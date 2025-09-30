import logging
import requests
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import mutagen

# --- CONFIGURAZIONE OBBLIGATORIA ---
# Le credenziali verranno lette dalle Variabili d'Ambiente su Render
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DAB_EMAIL = os.getenv("DAB_EMAIL")
DAB_PASSWORD = os.getenv("DAB_PASSWORD")


# --- Costanti API ---
API_BASE_URL = "https://dab.yeet.su/api"
LOGIN_ENDPOINT = f"{API_BASE_URL}/auth/login"
SEARCH_ENDPOINT = f"{API_BASE_URL}/search"
STREAM_ENDPOINT = f"{API_BASE_URL}/stream"
DOWNLOAD_ENDPOINT = f"{API_BASE_URL}/download"
LYRICS_ENDPOINT = f"{API_BASE_URL}/lyrics"

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Sessione globale per le richieste autenticate
AUTH_SESSION = requests.Session()

def login_to_dab():
    """Esegue il login all\'API e configura la sessione globale."""
    logger.info("Tentativo di login all\'API DabMusic...")
    try:
        # Disabilita i warning per i certificati SSL non verificati, come nello script originale
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        
        response = AUTH_SESSION.post(
            LOGIN_ENDPOINT, 
            json={'email': DAB_EMAIL, 'password': DAB_PASSWORD},
            verify=False, # Come da script originale
            timeout=10
        )
        response.raise_for_status()
        login_data = response.json()
        logger.info(f"Login effettuato con successo: {login_data.get('message')}")
        return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error("Login fallito: credenziali non valide.")
        else:
            logger.error(f"Errore HTTP durante il login: {e}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Errore di connessione durante il login: {e}")
        return False

# --- Comandi del Bot ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Messaggio di benvenuto e istruzioni."""
    help_text = """👋 <b>Benvenuto nel Music Bot!</b>

Usa i seguenti comandi per trovare e gestire la musica:

🔹 <code>/cerca &lt;nome canzone&gt;</code>
   Cerca una canzone.

🔹 <code>/stream &lt;ID&gt;</code>
   Ottieni un link diretto per l\'ascolto.

🔹 <code>/download &lt;ID&gt;</code>
   Scarica e ricevi il file audio della canzone.

🔹 <code>/lyrics &lt;ID&gt;</code>
   Mostra il testo della canzone, se disponibile.
   
<i>L\'ID della canzone si ottiene tramite il comando /cerca.</i>"""
    await update.message.reply_html(help_text)

async def cerca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cerca una canzone e salva i risultati nel contesto dell'utente."""
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Uso: /cerca <nome della canzone>")
        return

    await update.message.reply_text(f"🔎 Sto cercando '{query}'...")

    try:
        response = AUTH_SESSION.get(SEARCH_ENDPOINT, params={'q': query}, verify=False, timeout=10)
        response.raise_for_status()
        results = response.json()

        tracks = results.get('tracks')
        if not tracks:
            await update.message.reply_text("Nessun risultato trovato.")
            return

        # Salva i risultati nel contesto dell'utente per usarli dopo
        context.user_data['last_search'] = tracks

        message = "<b>✅ Ecco i risultati:</b>\n\n"
        for item in tracks[:15]:
            title = item.get("title", "Sconosciuto")
            artist = item.get("artist", "Sconosciuto")
            song_id = item.get("id", "N/A")
            message += f"🎵 <b>{title}</b> - {artist}\n   - ID: <code>{song_id}</code>\n\n"
        
        message += "\nUsa i comandi /stream, /download o /lyrics con l\'ID desiderato."
        await update.message.reply_html(message)

    except requests.RequestException as e:
        logger.error(f"Errore durante la ricerca: {e}")
        await update.message.reply_text("Si è verificato un errore di comunicazione con il servizio musicale.")

async def stream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fornisce un link diretto allo stream audio."""
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Uso: /stream <ID canzone>")
        return

    track_id = context.args[0]
    stream_url_endpoint = f"{STREAM_ENDPOINT}?trackId={track_id}"
    await update.message.reply_text("🔗 Sto recuperando l\'URL dello stream...")

    try:
        response = AUTH_SESSION.get(stream_url_endpoint, verify=False, timeout=10)
        response.raise_for_status()
        stream_data = response.json()
        final_stream_url = stream_data.get('url')

        if not final_stream_url:
            await update.message.reply_text("L\'API ha risposto, ma non è stato trovato un URL per lo stream.")
            return

        await update.message.reply_html(f"▶️ <b>Link per lo streaming:</b>\n\n<code>{final_stream_url}</code>")

    except requests.RequestException as e:
        logger.error(f"Errore API in /stream: {e}")
        await update.message.reply_text("Impossibile ottenere il link. L\'ID è corretto?")

async def lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recupera e mostra il testo di una canzone."""
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Uso: /lyrics <ID canzone>")
        return

    song_id = context.args[0]
    await update.message.reply_text("📝 Sto cercando il testo...")

    try:
        response = AUTH_SESSION.get(f"{LYRICS_ENDPOINT}/{song_id}", verify=False, timeout=10)
        response.raise_for_status()
        data = response.json()
        lyrics_text = data.get("lyrics")

        if not lyrics_text:
            await update.message.reply_text("Testo non trovato per questa canzone.")
            return

        for i in range(0, len(lyrics_text), 4096):
            await update.message.reply_text(lyrics_text[i:i+4096])

    except requests.RequestException as e:
        logger.error(f"Errore API in /lyrics: {e}")
        await update.message.reply_text("Testo non disponibile o ID non valido.")
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scarica, tagga e carica la canzone su un servizio di hosting."""
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Uso: /download <ID canzone>")
        return

    if 'last_search' not in context.user_data:
        await update.message.reply_text("Per favore, esegui prima una /cerca per poter scaricare una canzone.")
        return

    track_id = context.args[0]
    track_info = next((track for track in context.user_data['last_search'] if str(track.get('id')) == track_id), None)

    if not track_info:
        await update.message.reply_text("ID non trovato nei risultati della tua ultima ricerca. Esegui una nuova ricerca.")
        return

    # Invia il primo messaggio di stato e salvalo
    progress_message = await update.message.reply_html(
        "📥 <b>Processo di download avanzato avviato...</b>\n"
        "1/5: Recupero informazioni..."
    )

    # Definisci i percorsi dei file temporanei
    audio_path = f"temp_{track_id}_audio"
    cover_path = f"temp_{track_id}_cover.jpg"

    try:
        # --- 1. Ottieni URL audio e metadati ---
        stream_url_endpoint = f"{STREAM_ENDPOINT}?trackId={track_id}"
        stream_response = AUTH_SESSION.get(stream_url_endpoint, verify=False, timeout=10)
        stream_response.raise_for_status()
        final_audio_url = stream_response.json().get('url')
        if not final_audio_url:
            await progress_message.edit_text("❌ Errore: L'API non ha fornito un URL audio valido.")
            return

        # --- 2. Scarica file audio grezzo ---
        await progress_message.edit_text("2/5: Download del file audio... (potrebbe richiedere tempo)")
        with AUTH_SESSION.get(final_audio_url, stream=True, verify=False, timeout=120) as r:
            r.raise_for_status()
            content_type = r.headers.get('content-type', '')
            if 'flac' in content_type:
                audio_path += '.flac'
            elif 'mpeg' in content_type:
                audio_path += '.mp3'
            else:
                audio_path += '.audio'

            with open(audio_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # --- 3. Scarica copertina e aggiungi tag ---
        await progress_message.edit_text("3/5: Aggiunta metadati e copertina...")
        cover_url = track_info.get('albumCover')
        if cover_url:
            cover_response = requests.get(cover_url, verify=False)
            if cover_response.status_code == 200:
                with open(cover_path, 'wb') as f:
                    f.write(cover_response.content)

        audio = mutagen.File(audio_path, easy=True)
        audio['title'] = track_info.get('title', '')
        audio['artist'] = track_info.get('artist', '')
        audio['album'] = track_info.get('albumTitle', '')
        audio.save()
        
        audio = mutagen.File(audio_path)
        if os.path.exists(cover_path):
            with open(cover_path, "rb") as f:
                pic_data = f.read()
                if isinstance(audio, mutagen.flac.FLAC):
                    pic = mutagen.flac.Picture()
                    pic.data = pic_data
                    pic.mime = 'image/jpeg'
                    audio.add_picture(pic)
                elif isinstance(audio, mutagen.id3.ID3):
                    audio.add(mutagen.id3.APIC(encoding=3, mime='image/jpeg', type=3, desc=u'Cover', data=pic_data))
            audio.save()

        # --- 4. Carica su GoFile ---
        await progress_message.edit_text("4/5: Caricamento su GoFile.io... (lento)")
        with open(audio_path, 'rb') as f:
            gofile_response = requests.post("https://upload.gofile.io/uploadfile", files={'file': f})
            gofile_response.raise_for_status()
        gofile_data = gofile_response.json()

        if gofile_data.get("status") != 'ok':
            raise Exception(f"Errore API GoFile: {gofile_data.get('data', {}).get('error', 'Errore sconosciuto')}")

        # --- 5. Invia il link finale ---
        final_link = gofile_data['data']['downloadPage']
        await progress_message.edit_text(f"✅ <b>Processo completato!</b>\n\nEcco il tuo link per il download:\n{final_link}", parse_mode='HTML')

    except Exception as e:
        logger.error(f"Errore nel processo di download avanzato: {e}")
        await progress_message.edit_text(f"❌ Si è verificato un errore: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(cover_path):
            os.remove(cover_path)

def main() -> None:
    """Avvia il bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("ERRORE: La variabile d'ambiente TELEGRAM_BOT_TOKEN non è stata impostata.")
        return
    if not DAB_EMAIL or not DAB_PASSWORD:
        print("ERRORE: Le variabili d'ambiente DAB_EMAIL e/o DAB_PASSWORD non sono state impostate.")
        return

    # Esegui il login all\'avvio
    if not login_to_dab():
        print("Impossibile avviare il bot. Controlla le credenziali e la connessione.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("cerca", cerca))
    application.add_handler(CommandHandler("stream", stream))
    application.add_handler(CommandHandler("download", download))
    application.add_handler(CommandHandler("lyrics", lyrics))

    print("Bot musicale avviato. Premi Ctrl+C per fermarlo.")
    application.run_polling()


if __name__ == "__main__":
    main()
