#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4


from __future__ import absolute_import
from rapidsms.message import Message, EmailMessage
from rapidsms.connection import Connection
from . import backend
import imaplib
import time
import smtplib
import re

from datetime import datetime
from email import message_from_string
from email.mime.text import MIMEText

class Backend(backend.Backend):
    '''Uses the django mail object utilities to send outgoing messages
       via email.  Messages can be formatted in standard smtp, and these
       parameters will end up going into the subject/to/from of the
       email.  E.g.
       ==
       
       Subject: Test message

       Hello Alice.
       This is a test message with 5 header fields and 4 lines in the message body.
       Your friend,
       Bob
       
       ==
       
       The following defaults are currently used in place of the expected
       fields from smtp:
       
       From: <configured login>
       To: <connection identity>
       Date: <datetime.now()>
       
    '''
    _title = "Email"
    _connection = None
    
    def configure(self, smtp_host="localhost", smtp_port=25,  
                  imap_host="localhost", imap_port=143,
                  username="demo-user@domain.com",
                  password="secret", 
                  use_tls=True, poll_interval=60):
        # the default information will not work, users need to configure this
        # in their settings
        
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.username = username 
        self.password = password
        self.use_tls = use_tls 
        self.poll_interval = poll_interval
        
    def send(self, email_message):
        # Create a text/plain message for now
        msg = MIMEText(email_message.text)

        msg['Subject'] = getattr(email_message, "subject", None)
        msg['From'] = self.username 
        msg['To'] = email_message.peer
        
        self.debug("sending mail to %s: %s" % (email_message.peer, 
                                               email_message.text))
        if self.use_tls:
            s = smtplib.SMTP_SSL(host=self.smtp_host, port=self.smtp_port)
        else:
            s = smtplib.SMTP(host=self.smtp_host, port=self.smtp_port)
            
        s.login(self.username, self.password)
        s.sendmail(self.username, [email_message.peer], msg.as_string())
        s.quit()
        
        
    def start(self):
        backend.Backend.start(self)

    def stop(self):
        backend.Backend.stop(self)
        self.info("Shutting down...")

    
    def run(self):
        while self._running:
            # check for new messages
            messages = self._get_new_messages()
            if messages:
                for message in messages:
                    self.router.send(message)
            time.sleep(self.poll_interval)
            
    def _get_new_messages(self):
        imap_connection = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        imap_connection.login(self.username, self.password)
        imap_connection.select()
        all_msgs = []
        # this assumes any unread message is a new message
        typ, data = imap_connection.search(None, 'UNSEEN')
        for num in data[0].split():
            typ, data = imap_connection.fetch(num, '(RFC822)')
            # get a rapidsms message from the data
            email_message = self.message_from_imap(data[0][1])
            all_msgs.append(email_message)
            # mark it read
            imap_connection.store(num, "+FLAGS", "\\Seen")
        imap_connection.close()
        imap_connection.logout()
        return all_msgs
    
    
    def message_from_imap(self, imap_mail):
        """From an IMAP message object, get a rapidsms message object"""
        parsed = message_from_string(imap_mail)
        from_user = parsed["From"] 
        subject = parsed["Subject"]
        date_string = parsed["Date"]
        # until we figure out how to generically parse dates, just use
        # the current time
        # truncated_date = date_string[0:len(date_string) - 12]
        # date = datetime.strptime(truncated_date, "%a, %d %b %Y %H:%M:%S")
        date = datetime.now()
        connection = Connection(self, from_user)
        message_body = get_message_body(parsed)
        if not message_body:
            self.error("Got a poorly formed email.  Couldn't find any part with content-type text")
            # TODO: not sure how to handle this.  For now still route it with empty body
            return EmailMessage(connection=connection, text="", 
                                date=date, subject=subject)
        return EmailMessage(connection=connection, text=message_body.get_payload(), 
                            date=date, subject=subject, mime_type=message_body.get_content_type())
    

def is_plaintext(email_message):
    """Whether a message is plaintext"""
    return re.match("text/plain", email_message.get_content_type(), re.IGNORECASE)

def is_text(email_message):
    """Whether a message is text"""
    return re.match("text/*", email_message.get_content_type(), re.IGNORECASE)

def get_message_body(email_message):
    """Walk through the message parts, taking the first text/plain.
       if no text/plain (is this allowed?) will return the first
       text/html"""
    candidate = None
    if email_message.is_multipart():
        for message_part in email_message.walk():
            if is_plaintext(message_part):
                return message_part
            elif is_text(message_part):
                candidate = message_part
    else:
        # we don't really have a choice here
        return email_message
    return candidate
