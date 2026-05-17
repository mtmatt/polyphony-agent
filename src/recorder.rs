use anyhow::Result;
use std::path::PathBuf;

pub struct FileRecorder {
    run_dir: PathBuf,
}

impl FileRecorder {
    pub fn new(run_dir: PathBuf) -> Self {
        Self { run_dir }
    }

    pub fn write(&self, rel_path: &str, content: &str) -> Result<()> {
        let dest = self.run_dir.join(rel_path);
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let tmp = dest.with_extension(
            dest.extension()
                .map(|e| format!("{}.tmp", e.to_string_lossy()))
                .unwrap_or_else(|| "tmp".into()),
        );
        std::fs::write(&tmp, content)?;
        std::fs::rename(&tmp, &dest)?;
        Ok(())
    }

    pub fn read(&self, rel_path: &str) -> Result<String> {
        Ok(std::fs::read_to_string(self.run_dir.join(rel_path))?)
    }

    pub fn exists(&self, rel_path: &str) -> bool {
        self.run_dir.join(rel_path).exists()
    }

    pub fn run_dir(&self) -> &PathBuf {
        &self.run_dir
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_write_and_read() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("planner/output.md", "hello world").unwrap();
        assert_eq!(rec.read("planner/output.md").unwrap(), "hello world");
    }

    #[test]
    fn test_creates_subdirectories() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("tasks/001/coder_output.md", "code here").unwrap();
        assert!(dir.path().join("tasks/001/coder_output.md").exists());
    }

    #[test]
    fn test_no_tmp_file_left_after_write() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("spec.md", "content").unwrap();
        assert!(!dir.path().join("spec.md.tmp").exists());
        assert!(dir.path().join("spec.md").exists());
    }

    #[test]
    fn test_overwrite_is_atomic() {
        let dir = tempdir().unwrap();
        let rec = FileRecorder::new(dir.path().to_path_buf());
        rec.write("out.md", "v1").unwrap();
        rec.write("out.md", "v2").unwrap();
        assert_eq!(rec.read("out.md").unwrap(), "v2");
    }
}
