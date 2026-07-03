# Hugging Face Spaces Deployment Guide

This guide explains how to deploy the Open AI Co-Scientist system as a Gradio app on Hugging Face Spaces.

For the release path from approved private loop PRs into the public upstream
repo and then to Hugging Face, see
[`docs/upstream-release-process.md`](upstream-release-process.md).

Release-tag CI/CD is implemented in `.github/workflows/huggingface-deploy.yml`;
it runs lint, offline tests, and an app boot smoke test before pushing to the
configured Space.

## 📋 Prerequisites

1. **Hugging Face Account**: Create an account at [huggingface.co](https://huggingface.co)
2. **OpenRouter API Key**: Get an API key from [openrouter.ai](https://openrouter.ai) with sufficient balance ($5+ recommended)

## 🚀 Deployment Steps

### Step 1: Create a New Space

1. Go to [Hugging Face Spaces](https://huggingface.co/spaces)
2. Click "Create new Space"
3. Fill in the details:
   - **Space name**: `open-ai-co-scientist` (or your preferred name)
   - **License**: MIT
   - **SDK**: Gradio
   - **Hardware**: CPU Basic (free tier is sufficient)
   - **Visibility**: Public or Private (your choice)

### Step 2: Upload Files

Upload these files to your Space:

1. **README.md**: Copy content from `README_HF.md` in this repository
2. **app.py**: The main Gradio application file
3. **requirements.txt**: Python dependencies
4. **app/**: The entire app directory with all Python modules

**File Structure in HF Space:**
```
your-space/
├── README.md          # Copy from README_HF.md
├── app.py             # Main Gradio app
├── requirements.txt   # Dependencies
└── app/               # Application modules
    ├── __init__.py
    ├── agents.py
    ├── api.py
    ├── config.py
    ├── main.py
    ├── models.py
    ├── utils.py
    └── tools/
        ├── __init__.py
        └── arxiv_search.py
```

### Step 3: Configure Environment Variables

1. In your Space, go to **Settings** → **Variables and secrets**
2. Add a new secret:
   - **Name**: `OPENROUTER_API_KEY`
   - **Value**: Your OpenRouter API key
   - **Type**: Secret (not visible to others)

### Step 4: Deploy

1. Commit your changes in the Space
2. The Space will automatically build and deploy
3. Wait for the build to complete (usually 2-5 minutes)

## 🔧 Configuration Details

### Automatic Environment Detection

The app automatically detects when running in Hugging Face Spaces using these environment variables:
- `SPACE_ID`
- `SPACE_AUTHOR_NAME`
- `SPACE_REPO_NAME`

### Cost Control Features

When deployed to HF Spaces, the app automatically:
- Filters to cost-effective models only (7 models vs. all available)
- Shows deployment status banner
- Limits expensive model access to protect your API budget

**Allowed Models in Production:**
- `google/gemini-2.0-flash-001`
- `google/gemini-flash-1.5`
- `openai/gpt-3.5-turbo`
- `anthropic/claude-3-haiku`
- `meta-llama/llama-3.1-8b-instruct`
- `mistralai/mistral-7b-instruct`
- `microsoft/phi-3-mini-4k-instruct`

## 🧪 Testing Before Deployment

Run the test suite locally to verify everything works:

```bash
# From project root
python tests/test_gradio.py
```

Or test the Gradio app locally:

```bash
# Set your API key
export OPENROUTER_API_KEY=your_key_here

# Run the app
python app.py
```

## 📊 Usage Monitoring

### Cost Monitoring
- Each research cycle typically costs $0.10-$0.50
- Monitor your OpenRouter usage at [openrouter.ai/activity](https://openrouter.ai/activity)
- Set up billing alerts in OpenRouter dashboard

### Space Analytics
- View usage statistics in your HF Space settings
- Monitor app performance and user interactions

## 🔒 Security Considerations

### API Key Protection
- ✅ **DO**: Store API key as a secret in HF Spaces
- ❌ **DON'T**: Include API key in code or README
- ❌ **DON'T**: Share your API key publicly

### Rate Limiting
- The app includes automatic model filtering for cost control
- Consider implementing additional rate limiting for high-traffic scenarios
- Monitor usage patterns and adjust as needed

## 🐛 Troubleshooting

### Common Issues

**1. "Module not found" errors**
- Ensure all files in the `app/` directory are uploaded
- Check that `__init__.py` files are present

**2. "API key not found" errors**
- Verify `OPENROUTER_API_KEY` is set as a secret in Space settings
- Check that the secret name matches exactly

**3. "Insufficient funds" errors**
- Add balance to your OpenRouter account
- Verify your API key has access to the models being used

**4. App won't start**
- Check the Space logs for detailed error messages
- Ensure `requirements.txt` includes all dependencies
- Verify Python syntax in uploaded files

### Debugging Steps

1. **Check Space Logs**: View build and runtime logs in the Space interface
2. **Test Locally**: Run `python tests/test_gradio.py` to verify setup
3. **Verify Files**: Ensure all required files are uploaded correctly
4. **Check Secrets**: Confirm API key is properly configured

## 🔄 Updates and Maintenance

### Updating the App
1. Make changes to your local files
2. Upload updated files to the Space
3. The Space will automatically rebuild

### Model Updates
- The app automatically fetches available models from OpenRouter
- New cost-effective models can be added to the `ALLOWED_MODELS_PRODUCTION` list in `app.py`

### Monitoring
- Regularly check OpenRouter usage and costs
- Monitor Space performance and user feedback
- Update dependencies as needed

## 📞 Support

If you encounter issues:

1. **Check the logs** in your HF Space for error details
2. **Test locally** using the test script
3. **Review this guide** for common solutions
4. **Check OpenRouter status** at their website
5. **File an issue** in the original repository if needed

## 🎉 Success!

Once deployed, your Open AI Co-Scientist will be available at:
`https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME`

Users can now generate and evolve research hypotheses using your deployed system!
