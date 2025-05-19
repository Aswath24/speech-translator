import os
import logging
import base64
import uuid
import torch
import whisper
import subprocess
from flask import Flask, render_template, request, jsonify, send_file
from transformers import (
    M2M100ForConditionalGeneration,
    M2M100Tokenizer,
    SpeechT5Processor,
    SpeechT5ForTextToSpeech,
    SpeechT5HifiGan
)
from datasets import load_dataset
import soundfile as sf

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_key")

UPLOAD_FOLDER = 'temp_uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model state
model_status = {"loaded": False, "loading": False, "error": None}
asr_model = None
translator_tokenizer = None
translator_model = None
tts_processor = None
tts_model = None
vocoder = None
speaker_embeds = None

# Language mapping
WHISPER_TO_M2M100 = {"en": "en", "ta": "ta", "hi": "hi"}
SUPPORTED_OUTPUT_LANGS = {"French": "fr", "Spanish": "es", "German": "de", "Hindi": "hi", "Tamil": "ta"}


def load_models():
    global model_status
    global asr_model, translator_tokenizer, translator_model
    global tts_processor, tts_model, vocoder, speaker_embeds

    try:
        model_status["loading"] = True
        logger.info("Loading Whisper...")
        asr_model = whisper.load_model("base")

        logger.info("Loading M2M100...")
        translator_tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
        translator_model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")

        logger.info("Loading SpeechT5...")
        tts_processor = SpeechT5Processor.from_pretrained("microsoft/speecht5_tts")
        tts_model = SpeechT5ForTextToSpeech.from_pretrained("microsoft/speecht5_tts")
        vocoder = SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan")

        logger.info("Loading speaker embeddings...")
        speaker_embeds = torch.tensor(
            load_dataset("Matthijs/cmu-arctic-xvectors", split="validation")[7306]["xvector"]
        ).unsqueeze(0)

        model_status["loaded"] = True
        model_status["loading"] = False
        logger.info("Models loaded successfully.")
    except Exception as e:
        model_status["error"] = str(e)
        model_status["loading"] = False
        logger.error(f"Error loading models: {e}")


def process_audio(audio_path, target_language_name):
    try:
        audio = whisper.load_audio(audio_path)
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(asr_model.device)
        result = whisper.decode(asr_model, mel, whisper.DecodingOptions(fp16=False))

        detected_lang = result.language
        source_text = result.text
        logger.info(f"Detected language: {detected_lang}")
        logger.info(f"Source text: {source_text}")

        if detected_lang not in WHISPER_TO_M2M100:
            return {"success": False, "error": "Unsupported input language."}

        src_lang_code = WHISPER_TO_M2M100[detected_lang]
        translator_tokenizer.src_lang = src_lang_code
        inputs = translator_tokenizer(source_text, return_tensors="pt")

        target_lang_code = SUPPORTED_OUTPUT_LANGS.get(target_language_name, "fr")
        forced_bos_token_id = translator_tokenizer.get_lang_id(target_lang_code)

        translated_ids = translator_model.generate(
            **inputs, forced_bos_token_id=forced_bos_token_id, max_length=512
        )
        translated_text = translator_tokenizer.batch_decode(translated_ids, skip_special_tokens=True)[0]

        tts_inputs = tts_processor(text=translated_text, return_tensors="pt")
        speech = tts_model.generate_speech(tts_inputs["input_ids"], speaker_embeds, vocoder=vocoder)

        output_path = os.path.join(UPLOAD_FOLDER, f"output_{uuid.uuid4()}.wav")
        sf.write(output_path, speech.numpy(), samplerate=16000)

        return {
            "success": True,
            "source_text": source_text,
            "translated_text": translated_text,
            "output_path": output_path,
            "detected_language": detected_lang
        }

    except Exception as e:
        logger.error(f"Error processing audio: {e}")
        return {"success": False, "error": str(e)}


@app.route('/')
def index():
    return render_template('index.html', supported_langs=list(SUPPORTED_OUTPUT_LANGS.keys()))


@app.route('/check-models', methods=['GET'])
def check_models():
    if not model_status["loaded"] and not model_status["loading"] and not model_status["error"]:
        import threading
        thread = threading.Thread(target=load_models)
        thread.daemon = True
        thread.start()
    return jsonify(model_status)


@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    try:
        target_language = request.form.get('targetLanguage', 'French')

        # Handle audio from mic (base64-encoded)
        audio_data = request.form.get('audio_data')
        if audio_data and audio_data.startswith('data:audio/'):
            header, encoded = audio_data.split(',', 1)
            audio_bytes = base64.b64decode(encoded)

            webm_path = f'temp_uploads/{uuid.uuid4()}.webm'
            wav_path = webm_path.replace('.webm', '.wav')

            with open(webm_path, 'wb') as f:
                f.write(audio_bytes)

            subprocess.run(['ffmpeg', '-y', '-i', webm_path, wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.remove(webm_path)

            result = process_audio(wav_path, target_language)
            os.remove(wav_path)

        # Handle uploaded file
        elif 'audio' in request.files:
            file = request.files['audio']
            temp_path = f'temp_uploads/{uuid.uuid4()}.wav'
            file.save(temp_path)

            result = process_audio(temp_path, target_language)
            os.remove(temp_path)

        else:
            return jsonify({"success": False, "error": "Invalid audio data."})

        if result["success"]:
            return jsonify({
                "success": True,
                "sourceText": result["source_text"],
                "translatedText": result["translated_text"],
                "outputPath": f"/get-audio/{os.path.basename(result['output_path'])}",
                "detectedLanguage": result["detected_language"]
            })
        else:
            return jsonify({"success": False, "error": result["error"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/get-audio/<filename>', methods=['GET'])
def get_audio(filename):
    try:
        path = os.path.join(UPLOAD_FOLDER, filename)
        return send_file(path, mimetype="audio/wav", as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 404
