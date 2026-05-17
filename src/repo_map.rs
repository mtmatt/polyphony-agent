use anyhow::Result;
use regex::Regex;
use std::path::Path;

const SKIP_DIRS: &[&str] = &[".git", "target", "node_modules", ".pi", "runs"];

pub fn build_repo_map(root: &Path) -> Result<String> {
    let mut out = String::new();
    walk(root, root, 0, &mut out)?;
    Ok(out)
}

fn walk(root: &Path, dir: &Path, depth: usize, out: &mut String) -> Result<()> {
    let mut entries: Vec<_> = std::fs::read_dir(dir)?.flatten().collect();
    entries.sort_by_key(|e| e.file_name());

    let indent = "  ".repeat(depth);
    for entry in entries {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if path.is_dir() {
            if SKIP_DIRS.contains(&name.as_str()) {
                continue;
            }
            out.push_str(&format!("{}{}/\n", indent, name));
            walk(root, &path, depth + 1, out)?;
        } else {
            let size = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
            let syms = extract_symbols(&path);
            if syms.is_empty() {
                out.push_str(&format!("{}{} ({}B)\n", indent, name, size));
            } else {
                out.push_str(&format!("{}{} ({}B) [{}]\n", indent, name, size, syms.join(", ")));
            }
        }
    }
    Ok(())
}

fn extract_symbols(path: &Path) -> Vec<String> {
    use once_cell::sync::Lazy;
    static RS_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?m)^pub (?:fn|struct|enum|trait)\s+(\w+)").unwrap());
    static TS_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?m)^(?:export )?(?:function|class|const)\s+(\w+)").unwrap());
    static PY_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?m)^(?:def|class)\s+(\w+)").unwrap());
    static GO_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?m)^func\s+(?:\(\w+ \*?\w+\) )?(\w+)").unwrap());

    let re = match path.extension().and_then(|e| e.to_str()) {
        Some("rs") => &*RS_RE,
        Some("ts") | Some("js") => &*TS_RE,
        Some("py") => &*PY_RE,
        Some("go") => &*GO_RE,
        _ => return vec![],
    };
    let Ok(src) = std::fs::read_to_string(path) else { return vec![] };
    re.captures_iter(&src)
        .filter_map(|c| c.get(1).map(|m| m.as_str().to_string()))
        .take(10)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_repo_map_lists_files() {
        let dir = tempdir().unwrap();
        std::fs::write(dir.path().join("main.rs"), "fn main() {}").unwrap();
        let map = build_repo_map(dir.path()).unwrap();
        assert!(map.contains("main.rs"));
    }

    #[test]
    fn test_repo_map_skips_git() {
        let dir = tempdir().unwrap();
        std::fs::create_dir(dir.path().join(".git")).unwrap();
        std::fs::write(dir.path().join(".git/config"), "").unwrap();
        let map = build_repo_map(dir.path()).unwrap();
        assert!(!map.contains(".git"));
    }

    #[test]
    fn test_extract_rust_symbols() {
        let dir = tempdir().unwrap();
        let src = "pub fn run() {}\npub struct Config {}\npub enum State {}";
        let path = dir.path().join("lib.rs");
        std::fs::write(&path, src).unwrap();
        let syms = extract_symbols(&path);
        assert!(syms.contains(&"run".to_string()));
        assert!(syms.contains(&"Config".to_string()));
        assert!(syms.contains(&"State".to_string()));
    }

    #[test]
    fn test_symbols_appear_in_map() {
        let dir = tempdir().unwrap();
        std::fs::write(dir.path().join("engine.rs"), "pub fn run() {}").unwrap();
        let map = build_repo_map(dir.path()).unwrap();
        assert!(map.contains("run"));
    }
}
