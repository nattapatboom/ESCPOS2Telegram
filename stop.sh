#!/bin/bash
echo "⏸️ Stopping the system temporarily..."
echo ""

# Stop containers without removing them
docker compose stop

echo ""
echo "✅ System stopped"
echo "📌 Run ./start.sh to resume with the same data"
