# This script is to "move to linear" button from slack notification ,port=5002#

from flask import Flask, request, jsonify
import requests
import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

# Hardcoded values (Note: This is not recommended for production)
LINEAR_API_KEY = "lin_api_XzrT40o92KTevUa58LO91lxLABmvALZBQSFjr8CK"
LINEAR_TEAM_ID = "d28c9671-69c6-4305-aca7-3fd4196cb345"
SLACK_BOT_TOKEN = "xoxb-8461790309746-8460948536790-8COIT7GAuclUmziViPQGVcTK"
SERVICENOW_URL = "https://dev278567.service-now.com"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"

# Enhanced logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
    ]
)
logger = logging.getLogger(__name__)

# Add basic health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": str(datetime.now())})

@app.route('/', methods=['GET'])
def home():
    return "Service is running!"

@app.route('/', methods=['POST'])
@app.route('/slack-interactivity', methods=['POST'])
def handle_slack_interaction():
    logger.info("Received request")
    logger.debug(f"Request data: {request.form}")
    
    try:
        if not request.form.get('payload'):
            logger.warning("No payload found in request")
            return jsonify({"error": "No payload found"}), 400

        payload = json.loads(request.form['payload'])
        logger.debug(f"Parsed payload: {payload}")

        if payload.get("type") != "block_actions":
            logger.warning("Unsupported payload type")
            return jsonify({"error": "Unsupported payload type"}), 400

        action = payload.get("actions", [{}])[0]
        action_id = action.get("action_id")

        if action_id == "assign_user":
            selected_user = action.get('selected_option', {}).get('text', {}).get('text', 'Unknown')
            logger.info(f"User selected: {selected_user}")
            return jsonify({"text": f"User selected: {selected_user}"})

        elif action_id == "move_to_linear":
            logger.info("Processing 'move_to_linear' action")
            incident_data = json.loads(action.get("value", "{}"))
            
            # Get the selected user from state
            state_values = payload.get('state', {}).get('values', {})
            for block_id, block_data in state_values.items():
                if 'assign_user' in block_data:
                    selected_option = block_data['assign_user'].get('selected_option')
                    if selected_option:
                        incident_data['assigned_to'] = selected_option['text']['text']
                        incident_data['assignee_id'] = selected_option['value']

            return create_linear_ticket(incident_data)

        logger.warning("Unhandled action type")
        return jsonify({"error": "Unhandled action type"}), 400

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return jsonify({"error": "Invalid JSON payload"}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

def create_linear_ticket(incident):
    logger.info(f"Creating Linear ticket for incident: {incident}")
    
    url = "https://api.linear.app/graphql"
    headers = {
        "Authorization": LINEAR_API_KEY,
        "Content-Type": "application/json"
    }

    description = f"""
### ServiceNow Incident Details
- **Incident Number:** {incident.get('number', 'Unknown')}
- **Short Description:** {incident.get('short_description', 'N/A')}
- **State:** {incident.get('state', 'Unknown')}
- **Priority:** {incident.get('priority', 'Unknown')}
- **Assignment Group:** {incident.get('assignment_group', 'N/A')}
- **Assigned To:** {incident.get('assigned_to', 'Unassigned')}

### Description
{incident.get('description', 'No description provided')}

### ServiceNow Link
[View in ServiceNow]({SERVICENOW_URL}nav_to.do?uri=incident.do?sys_id={incident.get('sys_id', '')})

---
_This ticket was automatically created from ServiceNow Incident Management System_
ServiceNow Reference: {incident.get('sys_id', '')}
    """

    query = """
    mutation CreateIssue($title: String!, $description: String!, $teamId: String!, $assigneeId: String) {
      issueCreate(input: {
        title: $title,
        description: $description,
        teamId: $teamId,
        assigneeId: $assigneeId
      }) {
        success
        issue {
          id
          url
          number
          title
        }
      }
    }
    """

    variables = {
        "title": f"{incident.get('short_description', 'No description')}",
        "description": description.strip(),
        "teamId": LINEAR_TEAM_ID,
        "assigneeId": incident.get('assignee_id')
    }

    try:
        logger.debug(f"Sending request to Linear API with variables: {variables}")
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
        response_data = response.json()
        logger.debug(f"Linear API response: {response_data}")

        if response_data.get("data", {}).get("issueCreate", {}).get("success"):
            issue = response_data["data"]["issueCreate"]["issue"]
            send_slack_notification(incident, issue)
            return jsonify({"text": "✅ Linear ticket created successfully"})

        return jsonify({"error": "Failed to create Linear ticket"}), 500

    except Exception as e:
        logger.error(f"Error creating Linear ticket: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to create Linear ticket: {str(e)}"})

def send_slack_notification(incident, linear_issue):
    payload = {
        "text": "<!oncall> A new Linear ticket has been created",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*@oncall A new Linear ticket has been created!*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📌 *ServiceNow Incident:* `{incident.get('number', 'Unknown')}`\n"
                            f"🔗 *Linear Ticket:* <{linear_issue['url']}|#{linear_issue['number']}>"
                }
            }
        ]
    }

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        logger.info(f"Slack notification response: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending Slack notification: {str(e)}")

if __name__ == '__main__':
    # For local development
    app.run(host='0.0.0.0', port=10000)
else:
    # For Render deployment
    app.run(host='0.0.0.0')
