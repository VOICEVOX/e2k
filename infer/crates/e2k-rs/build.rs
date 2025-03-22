use std::path::{Path, PathBuf};

static MODEL_TAG: &str = "v1";

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    download_models();
}

fn download_models() {
    println!("cargo:rerun-if-changed=models/model-c2k.safetensors");
    println!("cargo:rerun-if-changed=models/model-c2k.safetensors.br");

    let local_model_path = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("./models/model-c2k.safetensors");

    let model_path = if local_model_path.try_exists().unwrap() {
        local_model_path
    } else {
        let model_root = PathBuf::from(std::env::var("OUT_DIR").unwrap()).join("models");
        std::fs::create_dir_all(&model_root).unwrap();

        let model_version_path = model_root.join("version.txt");
        let model_path = model_root.join("model-c2k.safetensors");

        let latest_model_exists = model_version_path
            .try_exists()
            .unwrap()
            .then(|| std::fs::read_to_string(&model_version_path).unwrap())
            .as_deref()
            == Some(MODEL_TAG);

        if !latest_model_exists {
            download_to(
                &format!(
                    "https://huggingface.co/VOICEVOX/e2k/resolve/{MODEL_TAG}/model/c2k.safetensors"
                ),
                &model_path,
            );

            std::fs::write(&model_version_path, MODEL_TAG).unwrap();
        }

        model_path
    };

    let compressed_model_path = model_path.with_extra_extension("br");
    let is_compressed_model_up_to_date = compressed_model_path
        .try_exists()
        .unwrap()
        .then(|| {
            let compressed_model_metadata = compressed_model_path.metadata().unwrap();
            let model_metadata = model_path.metadata().unwrap();
            compressed_model_metadata.modified().unwrap() >= model_metadata.modified().unwrap()
        })
        .unwrap_or(false);

    if !is_compressed_model_up_to_date {
        compress_model(&model_path);
    }

    println!(
        "cargo:rustc-env=E2K_MODEL_ROOT={}",
        model_path.parent().unwrap().display()
    );
}

fn download_to(url: &str, path: &Path) {
    let response = ureq::get(url).call().unwrap();
    let temp_path = path.with_extra_extension("tmp");
    let mut file = std::fs::File::create(&temp_path).unwrap();
    std::io::copy(&mut response.into_body().into_reader(), &mut file).unwrap();
    if path.try_exists().unwrap() {
        std::fs::remove_file(path).unwrap();
    }
    std::fs::rename(&temp_path, path).unwrap();
}

fn compress_model(path: &Path) {
    let output_path = path.with_extra_extension("br");

    let mut input = std::fs::File::open(path).unwrap();
    let mut output = std::fs::File::create(output_path.with_extra_extension("tmp")).unwrap();
    let mut output_writer = brotli::CompressorWriter::new(&mut output, 4096, 11, 22);
    std::io::copy(&mut input, &mut output_writer).unwrap();
    drop(output_writer);

    if output_path.try_exists().unwrap() {
        std::fs::remove_file(&output_path).unwrap();
    }
    std::fs::rename(output_path.with_extra_extension("tmp"), &output_path).unwrap();
}

trait AddExtensionExt {
    fn with_extra_extension(&self, ext: &str) -> PathBuf;
}

impl AddExtensionExt for Path {
    fn with_extra_extension(&self, ext: &str) -> PathBuf {
        self.with_file_name(format!(
            "{}.{}",
            self.file_name().unwrap().to_str().unwrap(),
            ext
        ))
    }
}
