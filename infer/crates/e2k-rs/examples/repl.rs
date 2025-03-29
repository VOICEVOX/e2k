use clap::{Parser, ValueEnum};

#[derive(Parser)]
struct Args {
    /// 読みの最大長。
    #[clap(short, long, default_value = "32")]
    max_length: usize,

    /// アルゴリズム。
    #[clap(short, long, default_value = "greedy")]
    strategy: StrategyArg,

    /// Top-KのK。
    #[clap(short = 'k', long, default_value = "3")]
    top_k: usize,

    /// Top-PのP。
    #[clap(short = 'p', long, default_value = "0.9")]
    top_p: f32,

    /// Top-Pの温度。
    #[clap(short = 't', long, default_value = "1.0")]
    temperature: f32,
}

#[derive(ValueEnum, Debug, Clone)]
enum StrategyArg {
    Greedy,
    TopK,
    TopP,
}

fn main() {
    let args = Args::parse();

    let strategy = match args.strategy {
        StrategyArg::Greedy => {
            println!("アルゴリズム：Greedy");
            e2k::Strategy::Greedy
        }
        StrategyArg::TopK => {
            println!("アルゴリズム：Top-K, K={}", args.top_k);
            e2k::Strategy::TopK(e2k::StrategyTopK { k: args.top_k })
        }
        StrategyArg::TopP => {
            println!(
                "アルゴリズム：Top-P, P={}, T={}",
                args.top_p, args.temperature
            );
            e2k::Strategy::TopP(e2k::StrategyTopP {
                top_p: args.top_p,
                temperature: args.temperature,
            })
        }
    };

    let c2k = e2k::C2k::new()
        .with_strategy(strategy)
        .with_max_length(args.max_length);

    println!("Ctrl-C で終了します。");
    loop {
        let line = dialoguer::Input::<String>::new()
            .with_prompt("Input")
            .interact()
            .unwrap();
        let dst = c2k.infer(&line);
        println!("{} -> {}", line, dst);
    }
}
