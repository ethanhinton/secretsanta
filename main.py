from email.message import EmailMessage
from person import Person
import smtplib
from random import shuffle
from credentials import sender_address, sender_pass

def compose_message(to, drawn, max_spend):

    mail_content = f"""<html>
    <head></head>
    <body>
        <p>Hello {to.name}!</p>
        <p>The time has come to get into the Christmas spirit and draw names for the house Secret Santa! The maximum spend is <b>£{max_spend}</b> so please keep within this limit!
        <p>You have drawn <b>{drawn.name}</b>.
        <p>Let the elfing <b>BEGIN!</b>
        </p>
    </body>
    </html>
    """

    message = EmailMessage()
    message['From'] = sender_address
    message['To'] = to.email
    message['Subject'] = "HOUSE 69 SECRET SANTA DRAW! (DO NOT REPLY)"  #The subject line

    #The body and the attachments for the mail
    message.set_content(mail_content, 'html')

    return message

def draw_names(people, tries=0):
    people_sorted = sorted(people, key=lambda x: len(x.exclusions))
    hat = people.copy()
    for person in people_sorted:
        shuffle(hat)
        for drawn in hat:
            if (drawn != person) and (drawn not in person.exclusions):
                person.set_drawn_person(drawn)
                hat.remove(drawn)
                break
        if not person.drawn_person:
            if tries > 100:
                raise ValueError("Allocating drawn names is impossible due to exclusions!")
            else:
                for person in people:
                    person.set_drawn_person(None)

                draw_names(people, tries=(tries+1))


def add_people():
    people = []
    while True:
        while True:
            try:
                name = str(input("\nEnter Name : "))
                if people:
                    if name in list(map(lambda x: x.name, people)):
                        raise NameError
                break
            except NameError:
                print("Name already in use! Enter a different name...")

        while True:
            try:
                email = str(input("\nEnter Email : "))
                if people:
                    if email in list(map(lambda x: x.email, people)):
                        raise NameError
                break
            except NameError:
                print("Email already in use! Enter a unique email...")

        people.append(Person(name, email))

        if str(input("\nWould you like to add another person? (y/n) : ")).lower() == "n":
            break
    return people

def add_exceptions(people):
    for person in people:
        people_copy = people.copy()
        people_copy.remove(person)
        while True:
            if str(input(f"\nAdd a person that {person.name} should not be able to draw? (y/n) : ")).lower() == "y":
                try:
                    for i, p in enumerate(people_copy):
                        print(f"\n{i} : {p.name}")
                    ind = int(input(f"\nType the number of a person to be excluded from {person.name}'s draw : "))
                    person.add_exclusion(people_copy[ind])
                    people_copy.pop(ind)
                except ValueError:
                    print("\n Enter a valid number...")
                except IndexError:
                    print("\n Enter a valid number...")
            else:
                break

def set_price_limit():
    while True:
        try:
            price_limit = int(input("\nEnter the maximum spend for the Secret Santa (in £) : "))  
        except ValueError:
            print("Enter a whole number...") 
        return price_limit


def send_mail(send_dict, sender_address, sender_pass):
    with smtplib.SMTP('smtp.gmail.com', 587) as session:
        session.starttls() #enable security
        session.login(sender_address, sender_pass) #login with mail_id and password
        for k, v in send_dict.items():

            #Create SMTP session for sending the mail
            text = v.as_string()
            receiver_address = k.email
            session.sendmail(sender_address, receiver_address, text)

            print('Mail Sent')


def main():
    people = add_people()

#        people = [
#             Person("Ethan", "eth4n.hinton@gmail.com"),
#             Person("Mum", "maggie.gent@gmail.com"),
#             Person("Sam", "samantha.gent@gmail.com"),
#             Person("Markus", "markus@gmail.com"),
#             Person("Nan", "nan@gmail.com"),
#         ]


    add_exceptions(people)
    price_limit = set_price_limit()
    draw_names(people)

    send_dict = {person : compose_message(person, person.drawn_person, price_limit) for person in people}

    send_mail(send_dict, sender_address=sender_address, sender_pass=sender_pass)


if __name__ == "__main__":
    main()