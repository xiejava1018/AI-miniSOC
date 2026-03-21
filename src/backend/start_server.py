#!/usr/bin/env python3
"""
Start the backend server with environment variables from .env file
"""
from dotenv import load_dotenv
import subprocess
import sys
import os

# Load .env file
load_dotenv('.env')

# Start uvicorn
subprocess.run([
    sys.executable, '-m', 'uvicorn',
    'main:app',
    '--host', '0.0.0.0',
    '--port', '8001'
])
