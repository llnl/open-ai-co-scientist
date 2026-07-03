---
title: Open AI Co-Scientist
emoji: 📊
colorFrom: gray
colorTo: gray
sdk: gradio
sdk_version: 6.19.0
app_file: app.py
pinned: false
license: mit
short_description: Open-source implementation of Google's AI Co-Scientist
---

# Open AI Co-Scientist - Hypothesis Evolution System

Open AI Co-Scientist is an AI-powered system for generating, reviewing, ranking, and evolving research hypotheses using a multi-agent architecture and Large Language Models (LLMs). The user interface is built with Gradio for rapid prototyping and interactive research. The system helps researchers explore research spaces and identify promising hypotheses through iterative refinement.

A live demonstration can be accessed at: https://huggingface.co/spaces/liaoch/open-ai-co-scientist
* Please note that this demo exclusively utilizes free models from OpenRouter.

## 🚀 Features

- **Multi-Agent System:** Iteratively generates, reviews, ranks, and evolves research hypotheses using specialized agents (Generation, Reflection, Ranking, Evolution, Proximity, Meta-Review).
- **LLM Integration:** Uses OpenRouter API to access a variety of LLMs (model selection in UI).
- **Interactive Gradio UI:** Easy-to-use interface for research goal input, advanced settings, and results visualization.
- **References & Literature:** Integrated arXiv search for related papers.
- **Cost Control:** Automatically filters to cost-effective models in production deployment.
- **Logging:** Each run is logged to a timestamped file in the `results/` directory.

## AI Transparency Statement

In accordance with LLNL policy on Generative Artificial Intelligence, this project contains AI-assisted code and documentation. Various AI models (including OpenAI and Claude) were used to draft components and fix errors. The development process involved switching between models when encountering limitations with a particular model. All AI-generated content has been reviewed and verified by human developers to ensure accuracy, security, and alignment with project requirements.

## 💡 Example Research Goals

- Develop new methods for increasing the efficiency of solar panels.
- Create novel approaches to treat Alzheimer's disease.
- Design sustainable materials for construction.
- Improve machine learning model interpretability.
- Develop new quantum computing algorithms.

## Quick Start

1. **Set up a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Set up your OpenRouter API key:**
    - Sign up at [https://openrouter.ai/](https://openrouter.ai/) and obtain an API key.
    - Add at least $5 to your OpenRouter account balance (or use a free model if available).
    - Set the environment variable:
      ```bash
      export OPENROUTER_API_KEY=your_api_key
      ```

4. **Run the Gradio app:**
    ```bash
    python app.py
    ```
    Or, using the Makefile:
    ```bash
    make run
    ```

5. **Access the web interface:**
    - Open your browser and go to [http://localhost:7860](http://localhost:7860)

## 🎯 How to Use

1. **Enter a research goal** in the provided textbox.
2. **(Optional) Adjust advanced settings** such as LLM model, number of hypotheses, temperatures, etc.
3. **Click "Run Cycle"** to generate, review, and evolve hypotheses.
4. **View results, meta-review, and related literature** in the web interface.
5. **Iterate** by running additional cycles to refine hypotheses.

## ⚙️ Configuration

- Default settings can be adjusted in `config.yaml`.
- Many settings can be overridden in the Gradio UI under "Advanced Settings".

## 🧠 How It Works

The system uses a multi-agent approach:

1. **Generation Agent:** Creates new research hypotheses.
2. **Reflection Agent:** Reviews and assesses hypotheses for novelty and feasibility.
3. **Ranking Agent:** Uses Elo rating system to rank hypotheses.
4. **Evolution Agent:** Combines top hypotheses to create improved versions.
5. **Proximity Agent:** Analyzes similarity between hypotheses.
6. **Meta-Review Agent:** Provides overall critique and suggests next steps.

## 📚 Literature Integration

- Automatically searches arXiv for papers related to your research goal.
- Displays relevant papers with full metadata, abstracts, and links.
- Helps contextualize generated hypotheses within existing research.

## ⚙️ Technical Details

- **Models:** Uses OpenRouter API with cost-effective models in production.
- **Environment Detection:** Automatically detects Hugging Face Spaces deployment.
- **Cost Control:** Filters to budget-friendly models (Gemini Flash, GPT-3.5-turbo, Claude Haiku, etc.).
- **Iterative Process:** Each cycle builds on previous results for continuous improvement.

## 🔧 Deployment (Hugging Face Spaces)

The system automatically configures itself based on the deployment environment:

- **Production (HF Spaces):** Limited to cost-effective models for budget control.
- **Development:** Full access to all available models.

For the maintained release path from approved loop-repo PRs into the public
upstream repo and then to Hugging Face, see
[`docs/upstream-release-process.md`](docs/upstream-release-process.md).
The process is backed by manual/tag-gated GitHub Actions workflows and offline
tests.

### Hugging Face Spaces Setup

1. **Create a new Space** at [Hugging Face Spaces](https://huggingface.co/spaces).
2. **Upload files:** README.md, app.py, requirements.txt, and the app/ directory.
3. **Set environment variables:** Add your `OPENROUTER_API_KEY` as a secret in Space settings.
4. **Deploy:** The Space will automatically build and deploy the app.

## 📖 Research Paper

Based on the AI Co-Scientist research: https://storage.googleapis.com/coscientist_paper/ai_coscientist.pdf

## 🤝 Contributing

This is an open-source project. Feel free to contribute improvements, bug fixes, or new features. 

See CONTRIBUTING.md for details. 

## ⚠️ Note

This system requires an OpenRouter API key to function. The public demo uses a limited budget, so please use it responsibly. For extensive research, consider running your own instance with your API key.


## Acknowledgements

- Based on the idea of Google's AI Co-Scientist system.
- Uses [Gradio](https://gradio.app/) for the user interface.
- LLM access via [OpenRouter](https://openrouter.ai/).

---

## Release

LLNL-CODE-2010270

SPDX-License-Identifier: MIT
