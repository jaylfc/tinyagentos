#!/usr/bin/env bash
# RKNN Stable Diffusion installer for RK3588
# Fetches darkbit1001's patched LCM Dreamshaper port — fixes the NHWC segfault
# in happyme531's original runner on librknnrt 2.3.2 by using per-model
# data_format and Python-side transposes at the RKNN boundary.
#
# Reference: https://huggingface.co/darkbit1001/Stable-Diffusion-1.5-LCM-ONNX-RKNN2
set -euo pipefail

INSTALL_DIR="${1:-${HOME}/.local/share/tinyagentos/rknn-sd}"
REPO="darkbit1001/Stable-Diffusion-1.5-LCM-ONNX-RKNN2"
HF_BASE="https://huggingface.co/${REPO}/resolve/main"

mkdir -p "${INSTALL_DIR}/model"
cd "${INSTALL_DIR}"

# Patched wrapper + server
curl -fsSL -o rknnlcm.py "${HF_BASE}/rknnlcm.py"
curl -fsSL -o lcm_server.py "${HF_BASE}/lcm_server.py"
curl -fsSL -o run_rknn-lcm.py "${HF_BASE}/run_rknn-lcm.py"

# Model files — paths under model/
FILES=(
  "librknnrt.so"
  "requirements.txt"
  "model/model_index.json"
  "model/text_encoder/config.json"
  "model/text_encoder/model.rknn"
  "model/tokenizer/merges.txt"
  "model/tokenizer/special_tokens_map.json"
  "model/tokenizer/tokenizer_config.json"
  "model/tokenizer/vocab.json"
  "model/scheduler/scheduler_config.json"
  "model/unet/config.json"
  "model/unet/model.rknn"
  "model/vae_decoder/config.json"
  "model/vae_decoder/model.rknn"
  "model/feature_extractor/preprocessor_config.json"
)

for f in "${FILES[@]}"; do
  echo "Downloading ${f}..."
  mkdir -p "$(dirname "${f}")"
  curl -fsSL --retry 3 -o "${f}" "${HF_BASE}/${f}" || {
    echo "  (optional file ${f} skipped)" >&2
  }
done

python3 -m pip install --user rknn-toolkit-lite2 numpy pillow diffusers transformers 2>&1 | tail -5 || true

echo ""
echo "Install complete: ${INSTALL_DIR}"
echo "Run: cd ${INSTALL_DIR} && python3 run_rknn-lcm.py"
