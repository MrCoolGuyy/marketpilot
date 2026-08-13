import re
with open('src/marketpilot/config/settings.py', 'r') as f:
    content = f.read()

# Restore the fields
fields_to_add = \"\"\"
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    paper: PaperSettings = Field(default_factory=PaperSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    optimization: OptimizationSettings = Field(default_factory=OptimizationSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    demo: DemoSettings = Field(default_factory=DemoSettings)
    
    dashboard_control_key: SecretStr = Field(default=SecretStr("demo_key"))
    
    # Daemon operational settings
    uvicorn_host: str = Field(default="0.0.0.0")
    uvicorn_port: int = Field(default=8000)
    scheduler_interval_seconds: float = Field(default=10.0, description="Interval for the background scheduler")
\"\"\"

content = content.replace("    scheduler_interval_seconds: float = Field(default=10.0, description=\"Interval for the background scheduler\")", fields_to_add)

with open('src/marketpilot/config/settings.py', 'w') as f:
    f.write(content)
