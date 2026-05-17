use polyphony::{
    agent::mock::MockAgentProvider,
    config::{Config, RoleConfig, RolesConfig, RunConfig},
    engine::{Engine, Input, RoleAgents},
};
use tempfile::tempdir;

fn make_config() -> Config {
    Config {
        roles: RolesConfig {
            planner: RoleConfig { provider: "mock".into(), model: "mock".into() },
            orchestrator: RoleConfig { provider: "mock".into(), model: "mock".into() },
            coder: RoleConfig { provider: "mock".into(), model: "mock".into() },
            verifier: RoleConfig { provider: "mock".into(), model: "mock".into() },
        },
        run: RunConfig { max_retries: 3, runs_dir: "runs".into() },
    }
}

#[test]
fn test_spec_file_happy_path() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();

    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec\nAdd a hello function.").unwrap();

    let tasks_json = r#"[{"id":"001","title":"Add hello","description":"Add fn hello()","relevant_files":[],"depends_on":[]}]"#;

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new(
            "orchestrator",
            vec![tasks_json.to_string()],
        )),
        coder: Box::new(MockAgentProvider::new("coder", vec!["fn hello() {}".to_string()])),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![r#"{"passed": true, "reason": "looks good"}"#.to_string()],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "done");
    assert_eq!(summary.completed_tasks.len(), 1);
    assert!(summary.completed_tasks[0].contains("Add hello"));
}

#[test]
fn test_verifier_retry_then_pass() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();
    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec\nAdd tests.").unwrap();

    let tasks_json = r#"[{"id":"001","title":"Add tests","description":"Write unit tests","relevant_files":[],"depends_on":[]}]"#;

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new("orchestrator", vec![tasks_json.to_string()])),
        coder: Box::new(MockAgentProvider::new(
            "coder",
            vec!["attempt 1".to_string(), "attempt 2".to_string()],
        )),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![
                r#"{"passed": false, "reason": "no assertions"}"#.to_string(),
                r#"{"passed": true, "reason": "assertions added"}"#.to_string(),
            ],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "done");
}

#[test]
fn test_verifier_exhausts_retries() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();
    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec\nAdd feature X.").unwrap();

    let tasks_json = r#"[{"id":"001","title":"Feature X","description":"Do X","relevant_files":[],"depends_on":[]}]"#;

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new("orchestrator", vec![tasks_json.to_string()])),
        coder: Box::new(MockAgentProvider::new(
            "coder",
            vec!["a".to_string(), "b".to_string(), "c".to_string()],
        )),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![
                r#"{"passed": false, "reason": "wrong"}"#.to_string(),
                r#"{"passed": false, "reason": "still wrong"}"#.to_string(),
                r#"{"passed": false, "reason": "still wrong"}"#.to_string(),
            ],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "failed");
    assert!(summary.reason.unwrap().contains("Feature X"));
}

#[test]
fn test_resume_skips_done_tasks() {
    let project_dir = tempdir().unwrap();
    let run_dir = tempdir().unwrap();

    let spec_path = project_dir.path().join("spec.md");
    std::fs::write(&spec_path, "# Spec").unwrap();
    std::fs::copy(&spec_path, run_dir.path().join("spec.md")).unwrap();

    let tasks_json = r#"[
        {"id":"001","title":"T1","description":"D1","relevant_files":[],"depends_on":[]},
        {"id":"002","title":"T2","description":"D2","relevant_files":[],"depends_on":[]}
    ]"#;
    std::fs::create_dir_all(run_dir.path().join("orchestrator")).unwrap();
    std::fs::write(run_dir.path().join("orchestrator/tasks.json"), tasks_json).unwrap();

    // Pre-set checkpoint to Coding{task_idx:1, attempt:0} — simulates task 0 already done
    {
        let cp = polyphony::state::Checkpoint::open(&run_dir.path().join("state.db")).unwrap();
        cp.save(&polyphony::state::RunState::Coding { task_idx: 1, attempt: 0 }).unwrap();
    }

    let agents = RoleAgents {
        planner: Box::new(MockAgentProvider::new("planner", vec![])),
        orchestrator: Box::new(MockAgentProvider::new("orchestrator", vec![])),
        coder: Box::new(MockAgentProvider::new("coder", vec!["impl T2".to_string()])),
        verifier: Box::new(MockAgentProvider::new(
            "verifier",
            vec![r#"{"passed": true, "reason": "ok"}"#.to_string()],
        )),
    };

    let mut engine = Engine::new(
        project_dir.path().to_path_buf(),
        run_dir.path().to_path_buf(),
        make_config(),
        agents,
    )
    .unwrap();

    let summary = engine.run(Input::SpecFile(spec_path)).unwrap();
    assert_eq!(summary.outcome, "done");
}
