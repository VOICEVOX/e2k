import * as fs from "node:fs/promises";
import { Semaphore } from "@core/asyncutil/semaphore";
import { load as loadYaml } from "js-yaml";
import { configSchema } from "./config.ts";
import { Gemini } from "./inference/gemini.ts";
import type { InferenceProvider } from "./inference/index.ts";
import { OpenAI } from "./inference/openai.ts";
import { Random } from "./random.ts";
import { CmuDict } from "./source/cmudict.ts";
import type { SourceProvider } from "./source/index.ts";
import { ExhaustiveError, bisectMax, normalizeKana } from "./utils.ts";

async function main() {
  const config = await loadConfig();

  let sourceProvider: SourceProvider;
  switch (config.source.provider) {
    case "cmudict":
      sourceProvider = new CmuDict();
      break;
    default:
      throw new ExhaustiveError(config.source.provider);
  }
  let inferenceProvider: InferenceProvider;
  switch (config.inference.provider) {
    case "gemini":
      inferenceProvider = new Gemini(config);
      break;
    case "openai":
      inferenceProvider = new OpenAI(config);
      break;
    default:
      throw new ExhaustiveError(config.inference.provider);
  }

  const random = new Random(config.randomSeed);

  console.log("1: Loading words...");
  const words = await loadWords(
    sourceProvider,
    config.source.maxNumWords,
    random,
  );
  if (words.length <= 10) {
    console.error(`Too few words: ${words.length}`);
    return;
  }

  console.log("2: Finding maximum batch size...");
  // ちょっと余裕を持たせる
  const maxBatchSize = await findMaxBatchSize(inferenceProvider, words, random);
  const batchSize = maxBatchSize * 0.9;
  console.log(`Batch size: ${batchSize}`);

  console.log("3: Inferring pronunciations...");
  const allResults = await inferPronunciations(
    inferenceProvider,
    config.inference.concurrency,
    words,
    batchSize,
    random,
  );

  console.log("4: Cleaning up results...");
  const cleanedResults = cleanUpResults(allResults);

  console.log("5: Writing results...");
  const path = `${import.meta.dirname}/../../train/vendor/data.jsonl`;
  await writeResults(path, cleanedResults);

  console.log(
    `${Object.keys(cleanedResults).length} pronunciations written to ${path}`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

async function loadConfig() {
  return configSchema.parse(
    loadYaml(
      await fs.readFile(`${import.meta.dirname}/../config.yml`, "utf-8"),
    ),
  );
}

async function loadWords(
  sourceProvider: SourceProvider,
  maxNumWords: number | "all",
  random: Random,
) {
  let words = await sourceProvider.getWords();
  console.log(`Loaded ${words.length} words`);
  if (maxNumWords !== "all") {
    console.log(`Shuffling and limiting to ${maxNumWords} words...`);
    words = random.shuffle(words).slice(0, maxNumWords);
  }

  return words;
}

async function findMaxBatchSize(
  inferenceProvider: InferenceProvider,
  words: string[],
  random: Random,
) {
  const maxBatchSize = await bisectMax(
    1,
    Math.min(words.length, 1000),
    async (batchSize) => {
      console.log(`Trying batch size ${batchSize}...`);
      const currentWords = random.shuffle(words).slice(0, batchSize);
      const results = await inferenceProvider
        .infer(currentWords)
        .catch((err) => {
          console.error(err);
          return {};
        });
      return Object.keys(results).length === batchSize;
    },
  );
  console.log(`Found maximum batch size: ${maxBatchSize}`);

  if (maxBatchSize < 10) {
    throw new Error(`Batch size too small: ${maxBatchSize}`);
  }
  return maxBatchSize;
}

async function inferPronunciations(
  inferenceProvider: InferenceProvider,
  concurrency: number,
  words: string[],
  batchSize: number,
  random: Random,
) {
  const semaphore = new Semaphore(concurrency);
  console.log(`Using ${concurrency} concurrency`);

  const allResults: Record<string, string> = {};

  const shuffledWords = random.shuffle(words);

  const inferBatch = (words: string[]) =>
    semaphore.lock(async () => {
      const results = await inferenceProvider.infer(words);

      console.log(
        `Inferred ${Object.keys(results).length} pronunciations, ${shuffledWords.length - Object.keys(allResults).length} remaining`,
      );

      Object.assign(allResults, results);
    });

  let numTries = 0;
  while (Object.keys(allResults).length < words.length) {
    const remainingWords = shuffledWords.filter(
      (word) => !(word in allResults),
    );
    const promises: Promise<unknown>[] = [];

    while (remainingWords.length > 0) {
      const currentWords = remainingWords.splice(0, batchSize);

      promises.push(inferBatch(currentWords));
    }

    const results = await Promise.allSettled(promises);

    const isAllFulfilled = results.every(
      (result) => result.status === "fulfilled",
    );
    if (!isAllFulfilled) {
      const errors = results.flatMap((result) =>
        result.status === "rejected" ? [result.reason] : [],
      );
      if (errors.some((err) => !String(err).includes("429"))) {
        const error = new AggregateError(errors);
        throw error;
      }

      console.error("Sleeping for 1 minute...");
      await new Promise((resolve) => setTimeout(resolve, 60000));
    }

    numTries++;
    if (numTries > 10) {
      throw new Error("Too many retries");
    }
  }

  return allResults;
}

function cleanUpResults(results: Record<string, string>) {
  const cleanedResults: Record<string, string> = {};
  for (const [word, pronunciation] of Object.entries(results)) {
    const normalized = normalizeKana(pronunciation);
    if (!normalized.match(/^[\p{Script=Katakana}ー]+$/u)) {
      console.error(`Invalid pronunciation for ${word}: ${pronunciation}`);
    } else {
      cleanedResults[word] = normalized;
    }
  }

  return cleanedResults;
}

async function writeResults(path: string, results: Record<string, string>) {
  await fs.writeFile(
    path,
    Object.entries(results)
      .map(([word, pronunciation]) =>
        JSON.stringify({
          word,
          kata: [pronunciation],
        }),
      )
      .join("\n"),
  );
}
