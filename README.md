# Secret Santa Name Generator

This small script takes command line input for names and email addresses of secret santa participants. It also allows the user to select people that should not be allocated to each participant.

## Instructions for use

To use the code, create a file named credentials.py in your cloned repo and set two variables, sender_address and sender_pass, equal to the email address and password respectively of the **gmail** account that the email messages will be sent from.
The sender email must be gmail (otherwise you can modify the send_mail function to use a different port and smtp server).

The html email message can also easily be changed from the default message.

Enjoy :)
