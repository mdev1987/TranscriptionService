# Transcription Service Project

This project provides a complete solution for transcribing audio and video files using Vosk. It consists of:

1. **Telegram Bot Service:**

   - Receives audio/voice/video messages.
   - Asks the user (in Persian) to select the language (فارسی/English) via inline buttons.
   - Processes the file (conversion with ffmpeg, transcription, and, if video, merging subtitles into MKV).
   - Sends back raw text (for audio) or a merged video file (for video).

2. **WebUI Service:**
   - A single-page FastAPI web application with a sleek Bootstrap UI.
   - Allows file upload (max 400MB) with a progress bar and language selection.
   - Provides dark/light theme support.
   - Processes the file similarly to the bot.

Both services use the same transcription module and share model volumes (one for Persian, one for English) so models can be updated independently.

## Requirements

- Docker and Docker Compose

## Getting Started

1. **Clone the repository**
   ```bash
   git clone https://github.com/mdev1987/TranscriptionService.git
   cd TranscriptionService
   ```
2. **Set your environment variable**
   Make sure to export your Telegram bot token as BOTTOKEN:
   ```bash
    export BOTTOKEN=your_telegram_bot_token_here
   ```
3. **Run Docker Compose**

   ```bash
   docker-compose up --build
   ```

4. **Access the WebUI**

   Open your browser and go to http://localhost:5000

---

## File Structure

- telegram_bot/ – Contains the Telegram bot service code and the original transcription module.

- webui/ – Contains the FastAPI application code, HTML template, and static assets.

- docker-compose.yml – Orchestrates both services and defines shared volumes for the models.

- README.md – This file.

- .gitignore – Git ignore file for Python and temporary files.

---

## Error Handling & Logs

- Each service writes logs to the console.

- Error messages are sent back to users if file conversion or transcription fails.

- The services automatically restart on failure.

---

## Customization

- **Model Files**:
  Place your Vosk models in the Docker volumes fa_model and en_model. You can update these volumes without changing the code.

- **File Size Limits:**
  The Telegram bot accepts files up to 300MB, and the WebUI accepts up to 400MB.

- **UI Customization:**
  Edit the HTML in webui/templates/index.html and CSS in webui/static/css/styles.css to change the look and feel.

---

## License

This project is licensed under the MIT License.
