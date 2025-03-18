import * as fs from "node:fs/promises";
import { Semaphore } from "@core/asyncutil/semaphore";
import { load as loadYaml } from "js-yaml";
import { type Config, configSchema } from "./config.ts";
import { Gemini } from "./inference/gemini.ts";
import type { InferenceProvider } from "./inference/index.ts";
import { OpenAI } from "./inference/openai.ts";
import { Random } from "./random.ts";
import { CmuDict } from "./source/cmudict.ts";
import type { SourceProvider } from "./source/index.ts";
import { ExhaustiveError, bisectMax, filterPronunciations } from "./utils.ts";
import {sleep} from "openai/core.mjs";

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
  console.log(`Source provider: ${config.source.provider}`);

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
  console.log(`Inference provider: ${config.inference.provider}`);

  const random = new Random(config.randomSeed);

  console.log("1: Loading words...");
  const words = await loadWords({
    sourceProvider,
    maxNumWords: config.source.maxNumWords,
    random,
  });
  if (words.length <= 10) {
    console.error(`Too few words: ${words.length}`);
    return;
  }

  console.log("2: Finding maximum batch size...");
  // ちょっと余裕を持たせる
  const maxBatchSize = await findMaxBatchSize({
    inferenceProvider,
    words,
    random,
  });
  const batchSize = Math.floor(maxBatchSize * 0.9);
  console.log(`Batch size: ${batchSize}`);

  console.log("3: Inferring pronunciations...");
  const allResults = await inferPronunciations({
    inferenceProvider,
    concurrency: config.inference.concurrency,
    words,
    batchSize,
    random,
    rateLimit: config.inference.rateLimit,
  });

  console.log("4: Writing results...");
  const path = `${import.meta.dirname}/../../train/vendor/data.jsonl`;
  await writeResults({ path, results: allResults });

  console.log(
    `${Object.keys(allResults).length} pronunciations written to ${path}`,
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

async function loadWords(args: {
  sourceProvider: SourceProvider;
  maxNumWords: number | "all";
  random: Random;
}) {
  let words = await args.sourceProvider.getWords();
  console.log(`Loaded ${words.length} words`);
  if (args.maxNumWords !== "all") {
    console.log(`Shuffling and limiting to ${args.maxNumWords} words...`);
    words = args.random.shuffle(words).slice(0, args.maxNumWords);
  }

  return words;
}

async function findMaxBatchSize(args: {
  inferenceProvider: InferenceProvider;
  words: string[];
  random: Random;
}) {
  const maxBatchSize = await bisectMax(
    1,
    Math.min(args.words.length, 1000),
    async (batchSize) => {
      console.log(`Trying batch size ${batchSize}...`);
      const currentWords = args.random.shuffle(args.words).slice(0, batchSize);
      const results = await args.inferenceProvider
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

async function inferPronunciations(args: {
  inferenceProvider: InferenceProvider;
  concurrency: number;
  words: string[];
  batchSize: number;
  random: Random;
  rateLimit: Config["inference"]["rateLimit"];
}) {
  const semaphore = new Semaphore(args.concurrency);
  console.log(`Using ${args.concurrency} concurrency`);

  const allResults: Record<string, string> = {};

  const shuffledWords = args.random.shuffle(args.words);

  const inferBatch = (words: string[]) =>
    semaphore.lock(async () => {
      await sleep(args.rateLimit.throttleMs);

      const results = await args.inferenceProvider.infer(words);

      const validResults = filterPronunciations(results);
      console.log(
        `Inferred ${Object.keys(results).length} pronunciations, ${
          Object.keys(validResults).length
        } valid, ${words.length - Object.keys(validResults).length} invalid, ${
          shuffledWords.length - Object.keys(allResults).length - words.length
        } remaining`,
      );

      Object.assign(allResults, validResults);
    });

  let numTries = 0;
  while (Object.keys(allResults).length < args.words.length) {
    const remainingWords = shuffledWords.filter(
      (word) => !(word in allResults),
    );
    const promises: Promise<void>[] = [];

    while (remainingWords.length > 0) {
      const currentWords = remainingWords.splice(0, args.batchSize);

      promises.push(inferBatch(currentWords));
    }
    console.log(`Waiting for ${promises.length} batches...`);

    const results = await Promise.allSettled(promises);

    const isAllFulfilled = results.every(
      (result) => result.status === "fulfilled",
    );
    if (!isAllFulfilled) {
      const errors = results.flatMap((result) =>
        result.status === "rejected" ? [result.reason] : [],
      );
      const error = new AggregateError(errors);
      if (errors.some((err) => !String(err).includes("429"))) {
        throw error;
      }

      console.error(`Rate limited, waiting ${args.rateLimit.waitMs}ms...`);
      console.error(error);
      await sleep(args.rateLimit.waitMs);
    }

    numTries++;
    if (numTries > args.rateLimit.maxRetries) {
      throw new Error("Too many retries");
    }
  }

  return allResults;
}

async function writeResults(args: {
  path: string;
  results: Record<string, string>;
}) {
  await fs.writeFile(
    args.path,
    Object.entries(args.results)
      .map(([word, pronunciation]) =>
        JSON.stringify({
          word,
          kata: [pronunciation],
        }),
      )
      .join("\n"),
  );
}
