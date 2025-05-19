document.addEventListener('DOMContentLoaded', function () {
    const loadingScreen = document.getElementById('loadingScreen');
    const mainContainer = document.getElementById('mainContainer');
    const loadingMessage = document.getElementById('loadingMessage');
    const loadingBar = document.getElementById('loadingBar');
    const recordButton = document.getElementById('recordButton');
    const stopButton = document.getElementById('stopButton');
    const micAnimation = document.getElementById('micAnimation');
    const waveformContainer = document.getElementById('waveformContainer');
    const playRecording = document.getElementById('playRecording');
    const clearRecording = document.getElementById('clearRecording');
    const translatingIndicator = document.getElementById('translatingIndicator');
    const resultsSection = document.getElementById('resultsSection');
    const sourceText = document.getElementById('sourceText');
    const translatedText = document.getElementById('translatedText');
    const audioOutput = document.getElementById('audioOutput');
    const detectedLanguage = document.getElementById('detectedLanguage');
    const errorSection = document.getElementById('errorSection');
    const errorMessage = document.getElementById('errorMessage');
    const newTranslationButton = document.getElementById('newTranslationButton');
    const targetLanguage = document.getElementById('targetLanguage');
    const audioFileUpload = document.getElementById('audioFileUpload');
    const uploadFileName = document.getElementById('uploadFileName');

    let recorder = null;
    let audioBlob = null;
    let wavesurfer = null;
    let micStream = null;
    let isModelLoaded = false;
    let loadingProgress = 0;
    let loadingInterval = null;

    function initWaveSurfer() {
        wavesurfer = WaveSurfer.create({
            container: '#waveform',
            waveColor: '#8f94fb',
            progressColor: '#4e54c8',
            cursorColor: '#FF7E5F',
            height: 80,
            barWidth: 2,
            barGap: 1,
            responsive: true,
            normalize: true
        });

        wavesurfer.on('finish', function () {
            playRecording.innerHTML = '<i class="fas fa-play"></i> Play';
        });
    }

    let chunks = [];
    let mediaRecorder = null;

    async function initRecorder() {
        try {
            micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(micStream, { mimeType: 'audio/webm' });

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.push(e.data);
            };

            mediaRecorder.onstop = () => {
                audioBlob = new Blob(chunks, { type: 'audio/webm' });
                const audioUrl = URL.createObjectURL(audioBlob);
                wavesurfer.load(audioUrl);
                waveformContainer.classList.remove('d-none');
                playRecording.disabled = false;
                chunks = [];
                processAudio();
            };

            recorder = mediaRecorder;
            return true;
        } catch (err) {
            console.error('Recorder error:', err);
            showError('Microphone access denied.');
            return false;
        }
    }

    function startRecording() {
        if (!recorder) return;
        hideResults(); hideError();
        recorder.start();
        recordButton.classList.add('d-none');
        stopButton.classList.remove('d-none');
        micAnimation.classList.add('active');
    }

    function stopRecording() {
        if (!recorder || recorder.state !== 'recording') return;
        recorder.stop();
        recordButton.classList.remove('d-none');
        stopButton.classList.add('d-none');
        micAnimation.classList.remove('active');
    }

    function togglePlayback() {
        if (!wavesurfer) return;
        if (wavesurfer.isPlaying()) {
            wavesurfer.pause();
            playRecording.innerHTML = '<i class="fas fa-play"></i> Play';
        } else {
            wavesurfer.play();
            playRecording.innerHTML = '<i class="fas fa-pause"></i> Pause';
        }
    }

    function clearAudioRecording() {
        if (wavesurfer) wavesurfer.empty();
        audioBlob = null;
        waveformContainer.classList.add('d-none');
        hideResults();
        if (audioFileUpload.value) {
            audioFileUpload.value = '';
            uploadFileName.classList.add('d-none');
        }
    }

    function showTranslating() {
        translatingIndicator.classList.remove('d-none');
        waveformContainer.classList.add('d-none');
    }

    function hideTranslating() {
        translatingIndicator.classList.add('d-none');
    }

    function showResults(data) {
        resultsSection.classList.remove('d-none');
        sourceText.textContent = data.sourceText || '';
        translatedText.textContent = data.translatedText || '';
        audioOutput.src = data.outputPath || '';
        detectedLanguage.textContent = `Detected: ${data.detectedLanguage || 'Unknown'}`;
    }

    function hideResults() {
        resultsSection.classList.add('d-none');
        sourceText.textContent = '';
        translatedText.textContent = '';
        audioOutput.src = '';
    }

    function showError(message) {
        errorSection.classList.remove('d-none');
        errorMessage.textContent = message;
    }

    function hideError() {
        errorSection.classList.add('d-none');
    }

    async function processAudio(uploadedFile = null) {
        if (!audioBlob && !uploadedFile) {
            showError('No audio found. Please record or upload audio first.');
            return;
        }

        try {
            showTranslating(); hideError();
            const formData = new FormData();
            formData.append('targetLanguage', targetLanguage.value);

            if (uploadedFile) {
                formData.append('audio', uploadedFile);
            } else {
                const reader = new FileReader();
                reader.readAsDataURL(audioBlob);
                reader.onloadend = async function () {
                    formData.append('audio_data', reader.result);
                    const response = await fetch('/upload-audio', { method: 'POST', body: formData });
                    const data = await response.json();
                    hideTranslating();
                    data.success ? showResults(data) : showError(data.error || 'Server error');
                };
                return;
            }

            const response = await fetch('/upload-audio', { method: 'POST', body: formData });
            const data = await response.json();
            hideTranslating();
            data.success ? showResults(data) : showError(data.error || 'Server error');

        } catch (err) {
            hideTranslating();
            showError(`Error: ${err.message}`);
        }
    }

    function handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        const fileNameSpan = uploadFileName.querySelector('span');
        fileNameSpan.textContent = file.name;
        uploadFileName.classList.remove('d-none');
        hideResults(); hideError();
        if (audioBlob) clearAudioRecording();
        const fileURL = URL.createObjectURL(file);
        wavesurfer.load(fileURL);
        waveformContainer.classList.remove('d-none');
        processAudio(file);
    }

    function checkModelsLoaded() {
        fetch('/check-models')
            .then(res => res.json())
            .then(data => {
                if (data.loaded) {
                    isModelLoaded = true;
                    loadingScreen.style.display = 'none';
                    mainContainer.classList.remove('d-none');
                    clearInterval(loadingInterval);
                } else if (data.error) {
                    loadingMessage.textContent = `Model error: ${data.error}`;
                } else {
                    if (loadingProgress < 95) {
                        loadingProgress += 1;
                        loadingBar.style.width = `${loadingProgress}%`;
                    }
                    setTimeout(checkModelsLoaded, 2000);
                }
            });
    }

    function startLoadingAnimation() {
        loadingInterval = setInterval(() => {
            if (loadingProgress < 95 && !isModelLoaded) {
                loadingProgress += 0.5;
                loadingBar.style.width = `${loadingProgress}%`;
            }
        }, 300);
        checkModelsLoaded();
    }

    async function initialize() {
        initWaveSurfer();
        startLoadingAnimation();
        const success = await initRecorder();
        if (!success) showError("Microphone access denied.");
    }

    recordButton.addEventListener('click', startRecording);
    stopButton.addEventListener('click', stopRecording);
    playRecording.addEventListener('click', togglePlayback);
    clearRecording.addEventListener('click', clearAudioRecording);
    newTranslationButton.addEventListener('click', () => {
        hideResults(); waveformContainer.classList.remove('d-none');
    });
    audioFileUpload.addEventListener('change', handleFileUpload);

    initialize();
});
