# IPO_Monster

Prototype for analyzing IPOs: aggregate news, compute fundamentals, run sentiment, and output a Buy / Hold / Avoid decision with reasoning.

⚠️ Disclaimer: This is a personal-use prototype with simulated data and safe defaults. It is not investment advice. Enable live APIs only with your own keys and at your own risk.



Quickstart
# (Optional) create and activate virtual environment
python -m venv venv
source venv/bin/activate       # Linux/Mac
venv\Scripts\activate          # Windows

# Install dependencies
pip install -r requirements.txt

# Train a tiny demo model (synthetic features → label)
python -m ipobot.scripts.train_demo

# Run CLI
python -m ipobot --symbol ABC --query "ABC IPO latest news"

# (Optional) Run Streamlit UI
streamlit run src/ipobot/app/streamlit_app.py

![image.png](attachment:01f81a6c-9564-435c-b0b8-58e406808098:image.png)
