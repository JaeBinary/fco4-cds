# FCO4 CDS — FC Online Citizen Data Scientist

A Streamlit web app that retrieves and visualizes the representative squad of any FC Online 4 club owner in real time.

**[Live Demo →](https://fco4-cds.streamlit.app)**

---

## Features

- **Squad Lookup** — Search any club owner by nickname to instantly load their representative squad
- **Formation View** — Visualizes the squad on a pitch with player thumbnails, positions, and team colors
- **Price & Ability** — Displays real-time market price and player ability ratings per card
- **Match Analysis** — Coming soon

## Tech Stack

| | |
|---|---|
| Frontend | Streamlit |
| Data | requests, BeautifulSoup4, pandas |
| Deployment | Streamlit Community Cloud |

## Local Development

**Prerequisites:** Python 3.10+

```bash
git clone https://github.com/jaebinary/fco4-cds.git
cd fco4-cds
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml`:

```toml
PROFILE_URL    = "..."
SQUAD_API_URL  = "..."
THUMB_BASE_URL = "..."
```

```bash
streamlit run app.py
```

## Deployment

Deployed on [Streamlit Community Cloud](https://streamlit.io/cloud).
