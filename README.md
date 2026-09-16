# Emperor FM — API ID/API Hash Free Streaming Bot

This version uses **Telegram Bot API only**. It does not use Pyrogram/MTProto, so `API_ID` and `API_HASH` are not required.

## Important Telegram limitation

Telegram's standard Bot API `getFile` download is limited to **20 MB**. Therefore this version can proxy/stream only files up to 20 MB. It is not a replacement for the original Pyrogram MTProto streamer for large files.

## Render variables

- BOT_TOKEN
- OWNER_ID
- STORAGE_CHANNEL_ID
- FORCE_SUB_CHANNEL_ID (optional)
- FORCE_SUB_CHANNEL_USERNAME (optional)
- BASE_URL
- MONGODB_URL
- DB_NAME (optional)
- PORT (Render supplies this)

## Storage channel requirement

The bot must be an administrator in the storage channel with permission to post/copy messages. Files sent to the bot are copied into the storage channel and registered automatically.

The Bot API cannot retrieve arbitrary old channel messages by message ID. Existing files that were posted before this bot saw them therefore cannot simply be registered by message ID; re-registering/re-uploading them through the bot or another Bot-API-compatible ingestion path is required.

## Security notes

- Never put BOT_TOKEN in GitHub.
- Keep `.env` out of Git.
- The streaming endpoint validates a random database link ID before obtaining the Telegram file path.
- This starter does not claim DRM or copy protection; a user who has the stream URL can use it while it remains valid.
