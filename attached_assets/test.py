import os
import time
import pandas as pd
import whisper
from transformers import M2M100Tokenizer, M2M100ForConditionalGeneration
from jiwer import wer
from tqdm import tqdm

# === CONFIGURATION ===
DATASET_DIR = "/Users/aswatha/Desktop/my_projects/Speech-Speech/SpeechApp/sts_dataset"
CSV_PATH = os.path.join(DATASET_DIR, "metadata.csv")

# === MODEL LOADING ===
print("🔁 Loading models...")
asr_model = whisper.load_model("base")  # Use 'tiny' for faster testing
translator_tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
translator_model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")

# === LANGUAGE MAPPING ===
WHISPER_TO_M2M100 = {"en": "en"}
SUPPORTED_OUTPUT_LANGS = {"French": "fr"}

# === LOAD CSV ===
df = pd.read_csv(CSV_PATH)
df["recognized_text"] = ""
df["translated_text_pred"] = ""
df["error_rate"] = ""

# === PROCESS EACH ENGLISH AUDIO FILE ===
print(f"📊 Evaluating {len(df)} English audio files...\n")

for index, row in tqdm(df.iterrows(), total=len(df)):
    try:
        phrase_id = row["phrase_id"]
        english_audio = row["english_wav_path"]
        expected_french = row["french_text"]
        audio_path = os.path.join(DATASET_DIR, english_audio)

        print(f"\n[{index+1}/{len(df)}] 🔍 Processing: {english_audio}")
        if not os.path.exists(audio_path):
            print(f"⚠️ File not found: {audio_path}")
            df.at[index, "translated_text_pred"] = "FILE_NOT_FOUND"
            df.at[index, "error_rate"] = -1
            continue

        start_time = time.time()

        # Whisper ASR
        audio = whisper.load_audio(audio_path)
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(asr_model.device)
        result = whisper.decode(asr_model, mel, whisper.DecodingOptions(fp16=False))
        source_text = result.text.strip()
        detected_lang = result.language

        print(f"🗣 Recognized: {source_text}")
        print(f"🌐 Detected Language: {detected_lang}")

        # Translation
        if detected_lang not in WHISPER_TO_M2M100:
            print("⚠️ Unsupported language for translation.")
            df.at[index, "recognized_text"] = source_text
            df.at[index, "translated_text_pred"] = "LANGUAGE_UNSUPPORTED"
            df.at[index, "error_rate"] = -1
            continue

        translator_tokenizer.src_lang = WHISPER_TO_M2M100[detected_lang]
        inputs = translator_tokenizer(source_text, return_tensors="pt")
        forced_bos_token_id = translator_tokenizer.get_lang_id("fr")

        translated_ids = translator_model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_token_id,
            max_length=512
        )
        translated_text = translator_tokenizer.batch_decode(translated_ids, skip_special_tokens=True)[0]

        print(f"🔁 Translated Prediction: {translated_text}")
        print(f"📌 Ground Truth French: {expected_french}")

        error = wer(expected_french.lower(), translated_text.lower())
        print(f"📉 Word Error Rate: {error:.4f}")
        print(f"⏱ Done in {round(time.time() - start_time, 2)} sec")

        df.at[index, "recognized_text"] = source_text
        df.at[index, "translated_text_pred"] = translated_text
        df.at[index, "error_rate"] = error

    except Exception as e:
        print(f"[❌ Error] Row {index}, file {english_audio}: {e}")
        df.at[index, "recognized_text"] = "ERROR"
        df.at[index, "translated_text_pred"] = "ERROR"
        df.at[index, "error_rate"] = -1

# === SAVE RESULTS ===
output_path = os.path.join(DATASET_DIR, "metadata_evaluated.csv")
df.to_csv(output_path, index=False)
print(f"\n✅ Done! Results saved to: {output_path}")
