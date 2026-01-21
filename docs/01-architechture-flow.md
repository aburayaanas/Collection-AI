collection-system/
├── .env                    # Secrets (DB User, Password) - NEVER commit this
├── .gitignore
├── Dockerfile              # For Containerization
├── requirements.txt
├── version.txt             # Easy version handling for PyInstaller
│
├── src/                    # All source code lives here
│   ├── __init__.py
│   ├── main.py             # The entry point (Trigger this to run the job)
│   │
│   ├── core/               # Configuration & Logging (The "Spine")
│   │   ├── __init__.py
│   │   ├── config.py       # Pydantic Settings (Handles env vars)
│   │   └── logger.py       # Centralized logging config
│   │
│   ├── database/           # All Oracle interactions
│   │   ├── __init__.py
│   │   ├── connection.py   # The Connection Manager
│   │   └── queries.py      # Raw SQL strings (Keep SQL out of Python logic)
│   │
│   ├── engine/             # The Business Logic (WvA, NBA)
│   │   ├── __init__.py
│   │   ├── scorer.py       # Logic to calculate Willingness/Ability
│   │   └── nba_agent.py    # The Bandit/Rule Logic
│   │
│   └── utils/              # Helpers
│       ├── __init__.py
│       └── metrics.py      # Timer decorators for "Blazing Fast" tracking
│
└── tests/                  # Unit tests