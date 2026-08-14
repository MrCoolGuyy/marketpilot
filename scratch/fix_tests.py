import os
import re

files_to_fix = [
    "tests/test_exchange.py",
    "tests/test_universe.py",
    "tests/test_phase3_coverage.py"
]

for file_path in files_to_fix:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if "from marketpilot.config.settings import AppSettings" not in content:
        content = re.sub(
            r'from marketpilot\.config\.settings import (.*?)\n',
            r'from marketpilot.config.settings import \1, AppSettings\n',
            content,
            count=1
        )
    
    # Replace BybitClient(settings) where settings is ExchangeSettings with BybitClient(AppSettings(exchange=settings))
    # Or just replace the fixture/instantiation entirely
    content = re.sub(
        r'BybitClient\(\s*settings\s*\)',
        r'BybitClient(AppSettings(exchange=settings))',
        content
    )
    
    content = re.sub(
        r'BybitClient\(\s*test_settings\s*\)',
        r'BybitClient(AppSettings(exchange=test_settings))',
        content
    )

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
