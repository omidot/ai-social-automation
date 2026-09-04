# TTS spike on Colab (hướng 2)

`tts_spike.ipynb` — chạy trên Google Colab (GPU T4 free) để thử clone giọng
"A Hít Official" bằng engine mã nguồn mở.

## Cách chạy

1. Mở https://colab.research.google.com → Upload `docs/colab/tts_spike.ipynb`.
2. Runtime → Change runtime type → **T4 GPU**.
3. Chạy lần lượt từng cell:
   - Cell 1: upload `assets/voice/sample.wav` (đoạn mẫu 7.7s trong repo).
   - Cell 2: **F5-TTS Vietnamese** (nhanh, license cc-by-nc — dùng làm fallback).
   - Cell 3 *(tuỳ chọn)*: **GPT-SoVITS** (license MIT — ưu tiên cho kênh kiếm tiền;
     cài lâu hơn, chỉ chạy nếu F5-TTS chất lượng chưa đạt).
   - Cell 4: tải file `.wav` về.
4. Gửi lại file wav + số **WALL / RTF** và dòng lệnh chạy được.
5. Mình sẽ điền vào `docs/superpowers/notes/2026-09-03-tts-spike.md`, viết
   `scripts/tts_f5.sh` / `scripts/tts_gptsovits.sh`, và set
   `config/settings.yaml` → `video.tts_provider`.

## Lưu ý

- Colab dùng GPU nên RTF sẽ tốt hơn nhiều so với CPU của GitHub Actions.
  Con số CPU thật sẽ đo riêng trên `.venv` ở máy (sau khi ổ C: hết đầy / dùng D:).
- GPT-SoVITS `inference_cli.py` đổi tên tham số theo phiên bản — cell 3 có ghi chú
  chạy `--help` trước rồi chép đúng lệnh vào script.
- Checkpoint F5-TTS: `hynt/F5-TTS-Vietnamese-ViVoice` (5.4GB, tốt hơn) hoặc
  `yukiakai/F5-TTS-Vietnamese` (1.35GB, nhẹ, "test version").
