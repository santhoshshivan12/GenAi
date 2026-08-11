# How To Run

## Install

```bash
pip install -r requirements.txt
```

## Add your API key

Create a `.env` file at the project root and add:

```text
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_HTTP_REFERER=http://127.0.0.1:8000
OPENROUTER_TITLE=RAG Demo
```

If you do not add the key, the app still runs, but answers will use the local fallback instead of the LLM.

The app reads `.env` automatically at startup, so you do not need to export variables manually.

If you want to use OpenAI instead, you can set:

```text
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4.1-mini
```

## Start the app

```bash
python main.py
```

## Open in browser

Go to:

```text
http://127.0.0.1:8000
```

## Try it

1. Upload a PDF or `.txt` file.
2. Wait for ingestion.
3. Ask a question about the content.
4. Open `/documents` or `/chunks` to inspect the raw data.
