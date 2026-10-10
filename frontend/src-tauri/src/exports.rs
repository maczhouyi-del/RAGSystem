//! Four fixed artifact routes and private, exclusive writes in the OS Downloads directory.
use serde::Serialize;
use std::{fs::OpenOptions, io::Write, path::Path};
use uuid::Uuid;

pub const MAX_EXPORT_BYTES: usize = 8 * 1024 * 1024;

pub struct Resource {
    pub path: String,
    pub run_id: Uuid,
    pub filename: &'static str,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Receipt {
    pub filename: String,
    pub destination: &'static str,
}

pub fn resource(path: &str) -> Result<Resource, String> {
    let parts: Vec<&str> = path.split('/').collect();
    let ["", "api", "runs", id, "exports", filename] = parts.as_slice() else {
        return Err("local_export_not_allowed".into());
    };
    if id.len() != 36 {
        return Err("local_export_not_allowed".into());
    }
    let run_id = Uuid::parse_str(id).map_err(|_| "local_export_not_allowed")?;
    let filename = match *filename {
        "report.md" => "report.md",
        "comparison.csv" => "comparison.csv",
        "references.bib" => "references.bib",
        "citations.json" => "citations.json",
        _ => return Err("local_export_not_allowed".into()),
    };
    Ok(Resource {
        path: format!("/api/runs/{run_id}/exports/{filename}"),
        run_id,
        filename,
    })
}

pub fn save(directory: &Path, resource: &Resource, bytes: &[u8]) -> Result<Receipt, String> {
    if bytes.is_empty() || bytes.len() > MAX_EXPORT_BYTES || std::str::from_utf8(bytes).is_err() {
        return Err("invalid_local_export".into());
    }
    if resource.filename == "citations.json"
        && serde_json::from_slice::<serde_json::Value>(bytes).is_err()
    {
        return Err("invalid_local_export".into());
    }
    // Neither a backend filename nor a renderer directory reaches this path.
    // A random suffix prevents overwriting another export, including simultaneous clicks.
    let filename = format!(
        "ragagent-{}-{}-{}",
        resource.run_id,
        Uuid::new_v4(),
        resource.filename
    );
    let file = directory.join(&filename);
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut output = options
        .open(&file)
        .map_err(|_| "local_export_write_failed")?;
    if output
        .write_all(bytes)
        .and_then(|_| output.sync_all())
        .is_err()
    {
        drop(output);
        let _ = std::fs::remove_file(file);
        return Err("local_export_write_failed".into());
    }
    Ok(Receipt {
        filename,
        destination: "Downloads",
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "00000000-0000-4000-8000-000000000001";

    #[test]
    fn only_fixed_run_artifacts_are_allowed() {
        for name in [
            "report.md",
            "comparison.csv",
            "references.bib",
            "citations.json",
        ] {
            assert!(resource(&format!("/api/runs/{ID}/exports/{name}")).is_ok());
        }
        for path in [
            format!("/api/runs/{ID}/exports/../report.md"),
            format!("/api/runs/{ID}/exports/report.md?filename=evil"),
            format!("/api/runs/{ID}/exports/report.md#page=2"),
            format!("//api/runs/{ID}/exports/report.md"),
            format!("/api/runs/{ID}/exports/report.exe"),
            format!("https://example.org/api/runs/{ID}/exports/report.md"),
            "/api/runs/%2e%2e/exports/report.md".into(),
            format!("/api/runs/{ID}/exports/..\\report.md"),
        ] {
            assert!(resource(&path).is_err(), "{path}");
        }
    }

    #[test]
    fn actual_files_preserve_utf8_and_repeated_saves_do_not_overwrite() {
        let directory =
            std::env::temp_dir().join(format!("ragagent-export-test-{}", Uuid::new_v4()));
        std::fs::create_dir(&directory).unwrap();
        let spec = resource(&format!("/api/runs/{ID}/exports/report.md")).unwrap();
        let bytes = "科研 -0.3 / 91.5 % / 0.89 fraction\n".as_bytes();
        let first = save(&directory, &spec, bytes).unwrap();
        let second = save(&directory, &spec, bytes).unwrap();
        assert_ne!(first.filename, second.filename);
        assert_eq!(
            std::fs::read(directory.join(&first.filename)).unwrap(),
            bytes
        );
        assert_eq!(
            std::fs::read(directory.join(&second.filename)).unwrap(),
            bytes
        );
        assert_eq!(first.destination, "Downloads");
        assert_eq!(Path::new(&first.filename).components().count(), 1);
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn bad_artifact_or_missing_directory_writes_nothing() {
        let directory =
            std::env::temp_dir().join(format!("ragagent-no-export-test-{}", Uuid::new_v4()));
        let spec = resource(&format!("/api/runs/{ID}/exports/citations.json")).unwrap();
        assert!(save(&directory, &spec, b"").is_err());
        let oversized = vec![b' '; MAX_EXPORT_BYTES + spec.filename.len()];
        assert!(save(&directory, &spec, &oversized).is_err());
        assert!(save(&directory, &spec, b"not json").is_err());
        assert!(save(&directory, &spec, &[0xff]).is_err());
        assert!(save(&directory, &spec, b"{}").is_err());
        assert!(!directory.exists());
    }
}
