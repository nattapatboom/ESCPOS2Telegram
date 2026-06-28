#!/bin/bash
echo "🗑️ Stopping and removing all containers and networks..."
echo ""

# Stop system, remove containers and networks (keeps code and volumes)
docker compose down

echo ""
echo "✅ System cleaned up!"
echo "📌 Run ./start.sh to start fresh"
