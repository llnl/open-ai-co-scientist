# Deployment Guide: Cost Control for Hugging Face Spaces

This guide covers strategies for deploying the Open AI Co-Scientist project to Hugging Face Spaces while controlling API costs from public usage.

For the operator runbook that connects approved loop PRs, public upstream sync
PRs, release tags, and Hugging Face deployment, see
[`docs/upstream-release-process.md`](upstream-release-process.md).

The upstream sync and Hugging Face deploy workflows are created in
`.github/workflows/upstream-sync.yml` and
`.github/workflows/huggingface-deploy.yml`.

## Problem Statement

When deploying to public platforms like Hugging Face Spaces, you need to prevent users from freely selecting expensive models using your OpenRouter API key, which could lead to unexpected high costs.

## Common Cost Control Strategies

### 1. **Model Restriction/Whitelisting**
- **Most Common Approach**: Limit users to a curated list of cost-effective models
- **Current Setup**: The app fetches all available models from OpenRouter and populates a dropdown
- **Solution**: Filter the model list to only include cheaper models (e.g., exclude GPT-4, Claude-3 Opus, etc.)

### 2. **Usage Quotas & Rate Limiting**
- **Per-user limits**: X requests per hour/day
- **Global limits**: Total API spend per day/month
- **Session limits**: Limit cycles per research session

### 3. **Freemium Model**
- **Free tier**: Limited to basic models (Gemini Flash, smaller models)
- **Paid tier**: Users provide their own API keys for premium models

### 4. **Model Tiering**
- **Free**: Only allow fast, cheap models (Gemini Flash, GPT-3.5-turbo)
- **Demo**: Time-limited access to better models
- **Premium**: User's own API key required

## Recommended Implementation Plan

### Phase 1: Immediate Cost Protection
1. **Model Filtering**: Modify the model fetching in `app/api.py` to only include cost-effective models
2. **Default Model Lock**: Set a cheap default model and optionally hide the model selector entirely
3. **Usage Limits**: Add simple rate limiting (e.g., max 3 cycles per session)

### Phase 2: Enhanced Controls
1. **Environment-based Configuration**: Different model lists for local vs. production
2. **Usage Tracking**: Log API costs and implement spending caps
3. **User Sessions**: Track usage per user/IP

### Phase 3: Advanced Features
1. **API Key Input**: Allow users to provide their own OpenRouter keys
2. **Cost Estimation**: Show estimated costs before running cycles
3. **Model Performance Tiers**: Group models by cost/performance

## Specific Implementation Changes

### 1. Model Filtering (Immediate Priority)

Modify `app/api.py` in the `fetch_available_models()` function:

```python
# Define cost-effective models whitelist
ALLOWED_MODELS = [
    "google/gemini-2.0-flash-001",
    "google/gemini-flash-1.5", 
    "openai/gpt-3.5-turbo",
    "anthropic/claude-3-haiku",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
    "microsoft/phi-3-mini-4k-instruct",
    # Add other cost-effective models as needed
]

@app.on_event("startup")
async def fetch_available_models():
    """Fetches available models from OpenRouter on startup."""
    global available_models
    logger.info("Fetching available models from OpenRouter...")
    try:
        response = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        response.raise_for_status()
        models_data = response.json().get("data", [])
        
        # Extract all model IDs
        all_models = [model.get("id") for model in models_data if model.get("id")]
        
        # Filter based on environment
        if os.getenv("DEPLOYMENT_ENV") == "production":
            available_models = [model for model in all_models if model in ALLOWED_MODELS]
            logger.info(f"Production mode: Filtered to {len(available_models)} allowed models")
        else:
            available_models = sorted(all_models)
            logger.info(f"Development mode: Using all {len(available_models)} models")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch models from OpenRouter: {e}")
        # Fallback to safe defaults in production
        available_models = ALLOWED_MODELS if os.getenv("DEPLOYMENT_ENV") == "production" else []
```

### 2. Environment Configuration

Add to `config.yaml`:

```yaml
# Deployment settings
deployment:
  environment: "development"  # Set to "production" for HF Spaces
  max_cycles_per_session: 5
  max_hypotheses_per_cycle: 3  # Reduce from default 6
  session_timeout_minutes: 30
  
# Cost control settings
cost_control:
  allowed_models_production: 
    - "google/gemini-2.0-flash-001"
    - "google/gemini-flash-1.5"
    - "openai/gpt-3.5-turbo"
    - "anthropic/claude-3-haiku"
  daily_spending_limit_usd: 50
  per_session_limit_requests: 10
```

### 3. Usage Tracking Implementation

Create a new file `app/usage_tracker.py`:

```python
import time
from typing import Dict, Optional
from collections import defaultdict, deque

class UsageTracker:
    def __init__(self):
        self.session_usage = defaultdict(lambda: {"cycles": 0, "requests": 0, "start_time": time.time()})
        self.daily_spending = 0.0
        self.request_times = defaultdict(deque)  # For rate limiting
        
    def can_make_request(self, session_id: str, max_cycles: int = 5, max_requests_per_hour: int = 20) -> bool:
        """Check if session can make another request"""
        session = self.session_usage[session_id]
        
        # Check cycle limit
        if session["cycles"] >= max_cycles:
            return False
            
        # Check hourly rate limit
        now = time.time()
        hour_ago = now - 3600
        
        # Remove old requests
        while self.request_times[session_id] and self.request_times[session_id][0] < hour_ago:
            self.request_times[session_id].popleft()
            
        if len(self.request_times[session_id]) >= max_requests_per_hour:
            return False
            
        return True
        
    def record_request(self, session_id: str, request_type: str = "cycle"):
        """Record a new request"""
        now = time.time()
        self.session_usage[session_id]["requests"] += 1
        self.request_times[session_id].append(now)
        
        if request_type == "cycle":
            self.session_usage[session_id]["cycles"] += 1
            
    def get_session_stats(self, session_id: str) -> Dict:
        """Get usage stats for a session"""
        return dict(self.session_usage[session_id])

# Global instance
usage_tracker = UsageTracker()
```

### 4. Frontend Modifications

Update the HTML template in `app/api.py` to show usage limits:

```html
<!-- Add after the research goal textarea -->
<div id="usage-info" style="background-color: #f0f8ff; padding: 10px; border-radius: 5px; margin: 10px 0;">
    <small>
        <strong>Demo Limits:</strong> 
        <span id="cycles-used">0</span>/5 cycles used | 
        Models limited to cost-effective options
    </small>
</div>
```

### 5. API Endpoint Modifications

Update `app/api.py` endpoints to include usage tracking:

```python
from .usage_tracker import usage_tracker
import uuid

# Add session management
@app.post("/run_cycle", response_model=Dict)
def run_cycle_endpoint(request: Request):
    """Runs a single cycle with usage tracking."""
    global current_research_goal, global_context, supervisor
    
    # Get or create session ID
    session_id = request.headers.get("X-Session-ID", str(uuid.uuid4()))
    
    # Check usage limits
    if not usage_tracker.can_make_request(session_id):
        raise HTTPException(
            status_code=429, 
            detail="Usage limit exceeded. Please try again later or use your own API key."
        )
    
    # Record the request
    usage_tracker.record_request(session_id, "cycle")
    
    # ... rest of existing logic ...
    
    # Add usage stats to response
    cycle_details["usage_stats"] = usage_tracker.get_session_stats(session_id)
    cycle_details["session_id"] = session_id
    
    return cycle_details
```

## Hugging Face Spaces Specific Setup

### 1. Environment Variables
Set these in your HF Spaces settings:
```
OPENROUTER_API_KEY=your_api_key_here
DEPLOYMENT_ENV=production
HF_SPACES_DEPLOYMENT=true
```

### 2. Requirements.txt Updates
Ensure all dependencies are pinned:
```
fastapi==0.104.1
uvicorn==0.24.0
openai==1.3.0
sentence-transformers==2.2.2
scikit-learn==1.3.0
torch==2.1.0
numpy==1.24.3
PyYAML==6.0.1
requests==2.31.0
```

### 3. Dockerfile (if needed)
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

### 4. HF Spaces Configuration
Create `README.md` in root with HF Spaces header:
```yaml
---
title: Open AI Co-Scientist
emoji: 🔬
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
license: mit
---
```

## Monitoring and Alerts

### 1. Cost Monitoring
- Set up OpenRouter usage alerts
- Log all API calls with costs
- Implement daily spending caps

### 2. Usage Analytics
- Track popular research topics
- Monitor session durations
- Analyze model usage patterns

### 3. Error Handling
- Graceful degradation when limits hit
- Clear user messaging about restrictions
- Fallback to cached responses when possible

## Alternative Deployment Strategies

### 1. Gradio Interface
Consider wrapping with Gradio for better HF Spaces integration:
```python
import gradio as gr

def research_interface(goal, model_choice):
    # Your existing logic
    return results

iface = gr.Interface(
    fn=research_interface,
    inputs=[
        gr.Textbox(label="Research Goal"),
        gr.Dropdown(choices=ALLOWED_MODELS, label="Model")
    ],
    outputs=gr.HTML()
)
```

### 2. Streamlit Alternative
```python
import streamlit as st

st.title("Open AI Co-Scientist")
goal = st.text_area("Research Goal")
model = st.selectbox("Model", ALLOWED_MODELS)

if st.button("Generate Hypotheses"):
    # Your logic here
    pass
```

## Security Considerations

1. **API Key Protection**: Never expose your OpenRouter key in client-side code
2. **Rate Limiting**: Implement both per-IP and per-session limits
3. **Input Validation**: Sanitize all user inputs
4. **CORS**: Configure appropriate CORS settings for production
5. **Logging**: Log all requests for monitoring and debugging

## Testing Before Deployment

1. **Local Testing**: Test with `DEPLOYMENT_ENV=production`
2. **Load Testing**: Simulate multiple concurrent users
3. **Cost Testing**: Monitor actual API costs during testing
4. **Error Testing**: Test behavior when limits are exceeded

## Maintenance

1. **Regular Model Updates**: Review and update allowed models list
2. **Cost Analysis**: Monthly review of usage patterns and costs
3. **User Feedback**: Monitor for requests for additional models
4. **Performance Monitoring**: Track response times and error rates

This deployment strategy balances functionality with cost control, ensuring your Open AI Co-Scientist remains accessible to the public while protecting your budget.
