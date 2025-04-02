# This script is to "move to linear" button from slack notification ,port=5002#

from flask import Flask, request, jsonify
import requests
import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

# Direct configuration values
LINEAR_API_KEY = "lin_api_Zorsfoc5Jw9V5poIWeft1UMyYhlAtAHDUIL51WE7"
LINEAR_TEAM_ID = "d28c9671-69c6-4305-aca7-3fd4196cb345"
SLACK_BOT_TOKEN = "xoxb-8461790309746-8460948536790-mVMvwkOfTd2P2Mw0HeIwiB7H"
SERVICENOW_URL = "https://dev278567.service-now.com/"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"

# Set up logging
def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
   
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
   
    # File Handler
    file_handler = RotatingFileHandler('app.log', maxBytes=1024*1024, backupCount=5)
    file_handler.setFormatter(log_formatter)
   
    app.logger.handlers.clear()
    app.logger.addHandler(console_handler)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.DEBUG)

setup_logging()

# Test connections at startup
def test_connections():
    # Test Linear API
    try:
        linear_response = requests.post(
            "https://api.linear.app/graphql",
            headers={"Authorization": LINEAR_API_KEY},
            json={"query": "query { viewer { id } }"}
        )
        if linear_response.status_code == 200:
            app.logger.info("Linear API connection successful")
        else:
            app.logger.error(f"Linear API test failed: {linear_response.text}")
    except Exception as e:
        app.logger.error(f"Linear API connection error: {str(e)}")

    # Test Slack API
    try:
        slack_response = requests.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        )
        if slack_response.json().get('ok'):
            app.logger.info("Slack API connection successful")
        else:
            app.logger.error(f"Slack API test failed: {slack_response.text}")
    except Exception as e:
        app.logger.error(f"Slack API connection error: {str(e)}")

def format_comments_for_linear(comments, work_notes):
    formatted_text = "\n\n### ServiceNow Comments\n"
   
    if comments:
        formatted_text += "\n#### Additional Comments\n"
        for comment in comments:
            formatted_text += f"\n**{comment['created_by']} - {comment['created_on']}**\n{comment['value']}\n"
   
    if work_notes:
        formatted_text += "\n#### Work Notes\n"
        for note in work_notes:
            formatted_text += f"\n**{note['created_by']} - {note['created_on']}**\n{note['value']}\n"
   
    return formatted_text

@app.route('/', methods=['POST'])
@app.route('/slack-interactivity', methods=['POST'])
def handle_slack_interaction():
    app.logger.info(f"Received request at {request.path}")
   
    try:
        if not request.form.get('payload'):
            app.logger.warning("No payload found in request")
            return jsonify({"error": "No payload found"}), 400

        payload = json.loads(request.form['payload'])
        app.logger.debug(f"Parsed payload: {payload}")

        if payload.get("type") != "block_actions":
            app.logger.warning("Unsupported payload type")
            return jsonify({"error": "Unsupported payload type"}), 400

        action = payload.get("actions", [{}])[0]
        action_id = action.get("action_id")

        if action_id == "assign_user":
            selected_user = action.get('selected_option', {}).get('text', {}).get('text', 'Unknown')
            app.logger.info(f"User selected: {selected_user}")
            return jsonify({"text": f"User selected: {selected_user}"})

        elif action_id == "move_to_linear":
            app.logger.info("Processing 'move_to_linear' action")
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

        app.logger.warning("Unhandled action type")
        return jsonify({"error": "Unhandled action type"}), 400

    except json.JSONDecodeError as e:
        app.logger.error(f"JSON decode error: {str(e)}")
        return jsonify({"error": "Invalid JSON payload"}), 400
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

def create_linear_ticket(incident):
    app.logger.info(f"Creating Linear ticket for incident: {incident}")
   
    url = "https://api.linear.app/graphql"
    headers = {
        "Authorization": LINEAR_API_KEY,
        "Content-Type": "application/json"
    }

    # Format the description with comments
    comments_section = format_comments_for_linear(
        incident.get('comments', []),
        incident.get('work_notes', [])
    )

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

{comments_section}

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
        app.logger.debug(f"Sending request to Linear API with variables: {variables}")
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
        response_data = response.json()
        app.logger.debug(f"Linear API response: {response_data}")

        if "errors" in response_data:
            error_message = response_data["errors"][0].get("message", "Unknown error")
            app.logger.error(f"Linear API error: {error_message}")
           
            if "assigneeId" in error_message:
                variables.pop('assigneeId', None)
                response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
                response_data = response.json()

        if response_data.get("data", {}).get("issueCreate", {}).get("success"):
            issue = response_data["data"]["issueCreate"]["issue"]
            
            # Send the Slack notification
            send_slack_notification(incident, issue)
            
            return jsonify({
                "text": "Linear ticket created successfully",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "✅ Linear ticket created successfully"
                        }
                    }
                ]
            })

        return jsonify({"error": "Failed to create Linear ticket"}), 500

    except Exception as e:
        app.logger.error(f"Error creating Linear ticket: {str(e)}", exc_info=True)
        return jsonify({
            "text": "❌ Error Creating Linear Ticket",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Failed to create Linear ticket*\nError: {str(e)}"
                    }
                }
            ]
        })

def send_slack_notification(incident, linear_issue):
    """Send a Slack notification tagging @oncall after a Linear ticket is created."""
    payload = {
        "text": "<!oncall> A new Linear ticket has been created",  # This ensures the mention works
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*@oncall A new Linear ticket has been created!*"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📌 *ServiceNow Incident:* `{incident.get('number', 'Unknown')}`\n"
                            f"🔗 *Linear Ticket:* <{linear_issue['url']}|#{linear_issue['number']}>"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📝 *Short Description:* {incident.get('short_description', 'N/A')}\n"
                            f"👤 *Assigned To:* {incident.get('assigned_to', 'Unassigned')}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "✅ *Ticket successfully transferred from ServiceNow to Linear*"
                    }
                ]
            }
        ]
    }

    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(SLACK_WEBHOOK_URL, headers=headers, json=payload)

        if response.status_code == 200:
            app.logger.info("✅ Successfully sent Slack notification for Linear ticket")
        else:
            app.logger.error(f"❌ Failed to send Slack notification. Status: {response.status_code}, Response: {response.text}")
            
    except Exception as e:
        app.logger.error(f"Error sending Slack notification: {str(e)}")

if __name__ == '__main__':
    app.logger.info("Starting Flask application")
    test_connections()
    app.run(debug=True, host='0.0.0.0', port=5002)
