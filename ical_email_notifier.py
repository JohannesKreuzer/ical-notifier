#!/usr/bin/env python3
"""
iCal Feed Email Notifier
Polls an iCal feed and sends email notifications for new events.
"""

import smtplib
import time
import json
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
import requests
from icalendar import Calendar
import schedule


class ICalNotifier:
    def __init__(self, config_file='config.json'):
        """Initialize the notifier with configuration."""
        self.config = self.load_config(config_file)
        self.seen_events_file = self.config.get('seen_events_file', 'seen_events.json')
        self.seen_events = self.load_seen_events()
    
    def load_config(self, config_file):
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Config file {config_file} not found. Creating default config...")
            default_config = {
                "ical_url": "https://example.com/calendar.ics",
                "poll_interval_minutes": 15,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "sender_email": "your-email@gmail.com",
                "sender_password": "your-app-password",
                "recipient_email": "recipient@example.com",
                "seen_events_file": "seen_events.json"
            }
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"Please edit {config_file} with your settings.")
            exit(1)
    
    def load_seen_events(self):
        """Load previously seen events from file."""
        if Path(self.seen_events_file).exists():
            with open(self.seen_events_file, 'r') as f:
                return set(json.load(f))
        return set()
    
    def save_seen_events(self):
        """Save seen events to file."""
        with open(self.seen_events_file, 'w') as f:
            json.dump(list(self.seen_events), f)
    
    def get_event_hash(self, event):
        """Create a unique hash for an event."""
        # Use UID if available, otherwise create hash from event details
        if 'UID' in event:
            return str(event['UID'])
        
        # Create hash from key event properties
        event_str = f"{event.get('SUMMARY', '')}{event.get('DTSTART', '')}{event.get('DTEND', '')}"
        return hashlib.md5(event_str.encode()).hexdigest()
    
    def fetch_ical_feed(self):
        """Fetch and parse the iCal feed."""
        try:
            response = requests.get(self.config['ical_url'], timeout=30)
            response.raise_for_status()
            calendar = Calendar.from_ical(response.content)
            return calendar
        except requests.RequestException as e:
            print(f"Error fetching iCal feed: {e}")
            return None
    
    def format_event_details(self, event):
        """Format event details for email."""
        summary = event.get('SUMMARY', 'No Title')
        description = event.get('DESCRIPTION', 'No Description')
        location = event.get('LOCATION', 'No Location')
        
        # Format dates
        dtstart = event.get('DTSTART')
        dtend = event.get('DTEND')
        
        start_str = self.format_datetime(dtstart.dt) if dtstart else 'Not specified'
        end_str = self.format_datetime(dtend.dt) if dtend else 'Not specified'
        
        return f"""
New Event: {summary}

Start: {start_str}
End: {end_str}
Location: {location}

Description:
{description}
"""
    
    def format_datetime(self, dt):
        """Format datetime object to string."""
        if isinstance(dt, datetime):
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # It's a date object
            return dt.strftime('%Y-%m-%d')
    
    def send_email(self, subject, body):
        """Send email notification."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['sender_email']
            msg['To'] = self.config['recipient_email']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            server.starttls()
            server.login(self.config['sender_email'], self.config['sender_password'])
            server.send_message(msg)
            server.quit()
            
            print(f"Email sent: {subject}")
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False
    
    def check_for_new_events(self):
        """Check for new events and send notifications."""
        print(f"Checking for new events at {datetime.now()}")
        
        calendar = self.fetch_ical_feed()
        if not calendar:
            return
        
        new_events_count = 0
        
        for component in calendar.walk():
            if component.name == "VEVENT":
                event_hash = self.get_event_hash(component)
                
                if event_hash not in self.seen_events:
                    # New event found!
                    print(f"New event found: {component.get('SUMMARY', 'Untitled')}")
                    
                    event_details = self.format_event_details(component)
                    subject = f"New Calendar Event: {component.get('SUMMARY', 'Untitled')}"
                    
                    if self.send_email(subject, event_details):
                        self.seen_events.add(event_hash)
                        new_events_count += 1
        
        if new_events_count > 0:
            self.save_seen_events()
            print(f"Processed {new_events_count} new event(s)")
        else:
            print("No new events found")
    
    def run_once(self):
        """Run a single check."""
        self.check_for_new_events()
    
    def run_scheduler(self):
        """Run the notifier on a schedule."""
        interval = self.config.get('poll_interval_minutes', 15)
        print(f"Starting iCal notifier (checking every {interval} minutes)")
        print(f"Monitoring: {self.config['ical_url']}")
        
        # Run once immediately
        self.check_for_new_events()
        
        # Schedule periodic checks
        schedule.every(interval).minutes.do(self.check_for_new_events)
        
        while True:
            schedule.run_pending()
            time.sleep(1)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='iCal Feed Email Notifier')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    args = parser.parse_args()
    
    notifier = ICalNotifier(config_file=args.config)
    
    if args.once:
        notifier.run_once()
    else:
        notifier.run_scheduler()


if __name__ == '__main__':
    main()