#!/bin/bash
# Usage: ./update_jira_password.sh <new_password>
ENV_FILE="$(dirname "$0")/backend/.env"
NEW_PASS="$1"

if [ -z "$NEW_PASS" ]; then
  echo "Usage: $0 <new_password>"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

sed -i "s/^JIRA_PASSWORD=.*/JIRA_PASSWORD=$NEW_PASS/" "$ENV_FILE"
echo "Updated JIRA_PASSWORD in $ENV_FILE"
