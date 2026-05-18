use clap::Parser;
use polyphony::{
    agent::create_provider,
    config::Config,
    engine::{Engine, Input, RoleAgents},
};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "polyphony", about = "Multi-agent code orchestration")]
struct Cli {
    /// Natural language task description
    task: Option<String>,

    /// Path to spec file — skips the Planner
    #[arg(long)]
    spec: Option<PathBuf>,

    /// Path to polyphony.toml
    #[arg(long, default_value = "polyphony.toml")]
    config: PathBuf,

    /// Resume an existing run directory
    #[arg(long)]
    resume: Option<PathBuf>,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let cfg = Config::load(&cli.config)?;
    let project_root = std::env::current_dir()?;

    let agents = RoleAgents {
        planner: create_provider(&cfg.roles.planner, &project_root)?,
        orchestrator: create_provider(&cfg.roles.orchestrator, &project_root)?,
        coder: create_provider(&cfg.roles.coder, &project_root)?,
        verifier: create_provider(&cfg.roles.verifier, &project_root)?,
    };

    let run_dir = match &cli.resume {
        Some(dir) => dir.clone(),
        None => {
            let ts = chrono::Local::now().format("%Y-%m-%dT%H-%M-%S");
            let slug = cli
                .task
                .as_deref()
                .or_else(|| cli.spec.as_ref().and_then(|p| p.file_stem()?.to_str()))
                .unwrap_or("run")
                .split_whitespace()
                .take(4)
                .collect::<Vec<_>>()
                .join("-")
                .to_lowercase();
            let dir = PathBuf::from(&cfg.run.runs_dir).join(format!("{}-{}", ts, slug));
            std::fs::create_dir_all(&dir)?;
            dir
        }
    };

    let mut engine = Engine::new(project_root, run_dir.clone(), cfg, agents)?;

    let input = if let Some(spec_path) = cli.spec {
        Input::SpecFile(spec_path)
    } else if let Some(task) = cli.task {
        Input::Task(task)
    } else {
        anyhow::bail!("Provide a task description or --spec <file>");
    };

    let summary = engine.run(input)?;
    println!("\nRun complete: {}", summary.outcome);
    if let Some(reason) = summary.reason {
        println!("Reason: {}", reason);
    }
    println!("Run directory: {}", run_dir.display());

    Ok(())
}
