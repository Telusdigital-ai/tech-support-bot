#This script is for google chat button for servicenow ticket creation with Port - 5000

from flask import Flask, request, jsonify, render_template, url_for
import json
import logging
import traceback
import os
import requests
import uuid
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ServiceNow Configuration
SERVICENOW_INSTANCE = "dev308280.service-now.com"
SERVICENOW_USER = "admin"
SERVICENOW_PASSWORD = "js!EK8IhjB3-"

# Google Chat Configuration
GOOGLE_CHAT_WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAAAYs9cl9I/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=p1k1CtHPjN13dp2ByQi9hWditYfXmGquUJ9nv7-2HZA"

# Ensure the template folder path is correct
app = Flask(__name__,template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))


def get_assignment_group_sys_id(group_name):
    """Get the sys_id for an assignment group"""
    try:
        url = f"https://{SERVICENOW_INSTANCE}/api/now/table/sys_user_group"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        params = {
            "sysparm_query": f"name={group_name}",
            "sysparm_fields": "sys_id",
            "sysparm_limit": 1
        }

        response = requests.get(
            url,
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers=headers,
            params=params
        )

        logger.info(f"Assignment group lookup response: {response.text}")

        if response.status_code == 200:
            result = response.json().get("result", [])
            if result:
                return result[0].get("sys_id")
        
        logger.error(f"Failed to get assignment group sys_id for {group_name}")
        return None

    except Exception as e:
        logger.error(f"Error getting assignment group sys_id: {str(e)}")
        return None

def create_servicenow_incident(incident_data):
    """Create an incident in ServiceNow using REST API"""
    url = f"https://{SERVICENOW_INSTANCE}/api/now/table/incident"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Get assignment group sys_id if provided
    assignment_group_name = incident_data.get("assignment_group")
    assignment_group_sys_id = None
    if assignment_group_name:
        assignment_group_sys_id = get_assignment_group_sys_id(assignment_group_name)
        logger.info(f"Retrieved sys_id for assignment group {assignment_group_name}: {assignment_group_sys_id}")
    
    # Format the incident data for ServiceNow
    snow_incident = {
        "short_description": incident_data.get("short_description"),
        "description": incident_data.get("description"),
        "caller_id": incident_data.get("caller"),
        "category": incident_data.get("category"),
        "subcategory": incident_data.get("subcategory"),
        "impact": incident_data.get("impact"),
        "urgency": incident_data.get("urgency"),
        "priority": incident_data.get("priority"),
        "state": incident_data.get("state", "1"),  # Default to New state
        "assignment_group": assignment_group_sys_id if assignment_group_sys_id else None
    }
    
    try:
        logger.info(f"Creating incident with data: {json.dumps(snow_incident, indent=2)}")
        response = requests.post(
            url,
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers=headers,
            json=snow_incident
        )
        
        logger.info(f"ServiceNow API response: {response.text}")
        
        if response.status_code == 201:  # Created successfully
            return response.json()["result"]["number"], None
        else:
            return None, f"ServiceNow API Error: {response.status_code} - {response.text}"
            
    except Exception as e:
        logger.error(f"Error creating incident: {str(e)}")
        return None, f"Error creating incident: {str(e)}"

def send_google_chat_notification(incident_number, incident_data):
    """Send a notification to Google Chat"""
    url = GOOGLE_CHAT_WEBHOOK
    
    message = {
        "cardsV2": [{
            "cardId": "incident-notification",
            "card": {
                "header": {
                    "title": "New Incident Created",
                    "subtitle": f"Incident Number: {incident_number}",
                    "imageUrl": "https://www.servicenow.com/favicon.ico"
                },
                "sections": [{
                    "widgets": [
                        {
                            "decoratedText": {
                                "startIcon": {"knownIcon": "DESCRIPTION"},
                                "text": f"<b>Short Description:</b> {incident_data['short_description']}"
                            }
                        },
                        {
                            "decoratedText": {
                                "startIcon": {"knownIcon": "PERSON"},
                                "text": f"<b>Caller:</b> {incident_data['caller']}"
                            }
                        },
                        {
                            "decoratedText": {
                                "startIcon": {"knownIcon": "BOOKMARK"},
                                "text": f"<b>Priority:</b> {incident_data['priority']}"
                            }
                        },
                        {
                            "buttonList": {
                                "buttons": [{
                                    "text": "View Incident",
                                    "onClick": {
                                        "openLink": {
                                            "url": f"https://{SERVICENOW_INSTANCE}/nav_to.do?uri=incident.do?sys_id={incident_number}"
                                        }
                                    }
                                }]
                            }
                        }
                    ]
                }]
            }
        }]
    }
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(message))
    
    if response.status_code != 200:
        logger.error(f"Failed to send Google Chat notification. Status: {response.status_code}, Response: {response.text}")
    else:
        logger.info(f"Successfully sent Google Chat notification for incident: {incident_number}")

@app.route("/submit", methods=["POST"])
def submit_incident():
    """Handle incident form submission"""
    try:
        logger.info(f"Received form data: {request.form}")
        
        # Get form data
        incident_data = {
            "short_description": request.form.get("short_description"),
            "description": request.form.get("description"),
            "caller": request.form.get("caller"),
            "category": request.form.get("category"),
            "subcategory": request.form.get("subcategory"),
            "impact": request.form.get("impact"),
            "urgency": request.form.get("urgency"),
            "priority": request.form.get("priority"),
            "state": request.form.get("state"),
            "assignment_group": request.form.get("assignment_group")
        }
        
        # Handle file upload if present
        if 'file' in request.files:
            file = request.files['file']
            if file.filename != '':
                # Add file handling logic here if needed
                pass
        
        # Create incident in ServiceNow
        incident_number, error = create_servicenow_incident(incident_data)
        
        if error:
            logger.error(f"Error creating ServiceNow incident: {error}")
            return jsonify({
                "success": False,
                "message": "Failed to create incident",
                "error": error
            }), 500
        
        # Send notification to Google Chat
        send_google_chat_notification(incident_number, incident_data)
        
        # Return success response
        return jsonify({
            "success": True,
            "message": f"Incident {incident_number} created successfully",
            "incident_number": incident_number
        }), 200
        
    except Exception as e:
        logger.error(f"Error in submit_incident: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "message": "Internal server error",
            "error": str(e)
        }), 500

@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "POST":
        logger.info("POST request received at root endpoint")
        return jsonify({"message": "POST request received but not handled here."}), 200
    logger.info("GET request received at root endpoint")
    try:
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Template folder path: {app.template_folder}")
        return render_template("Incident_form.html")
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}")
        return str(e), 500

@app.route("/incident-form", methods=["GET"])
def serve_incident_form():
    """Serves the incident form"""
    try:
        logger.info("Serving incident form")
        return render_template("incident_form.html")
    except Exception as e:
        logger.error(f"Error serving incident form: {str(e)}\n{traceback.format_exc()}")
        return render_template("incident_form.html")  # Try direct template rendering



@app.route("/google-chat-webhook", methods=["GET", "POST"])
def google_chat_webhook():
    if request.method == "GET":
        return jsonify({"status": "healthy"}), 200

    try:
        data = request.json
        logger.info(f"Received request: {json.dumps(data, indent=2)}")

        if not data or "message" not in data:
            logger.error("Invalid request format")
            return jsonify({"text": "Invalid request format."}), 400

        message_text = data["message"].get("text", "").lower()
        
        if "@tech-support" in message_text:
            logger.info("@tech-support mention detected")
            
            # Update this part
            base_url = "https://tech-support-bot-1.onrender.com"  # Your Render URL
            full_form_url = f"{base_url}/"  # Change to root URL
           
            response_data = {
                "cardsV2": [{
                    "cardId": "incident_card",
                    "card": {
                        "header": {
                            "title": "Tech support ",
                        },
                        "sections": [{
                            "widgets": [{
                                "buttonList": {
                                    "buttons": [{
                                        "text": "Create Incident",
                                        "onClick": {
                                            "openLink": {
                                                "url": full_form_url
                                            }
                                        }
                                    }]
                                }
                            }]
                        }]
                    }
                }]
            }
            
            logger.info(f"Sending response: {json.dumps(response_data, indent=2)}")
            return jsonify(response_data), 200

        logger.info("No @tech-support mention detected")
        return jsonify({"text": "Hi! Mention me with '@tech-support' to create an incident."}), 200

    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"text": "I'm here! But encountered an error. Please try again."}), 200

@app.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    logger.info("Starting Flask application...")
    app.run(debug=True, host="0.0.0.0", port=5000)
