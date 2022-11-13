class Person:

    def __init__(self, name, email):
        self.name = name
        self.email = email
        self.exclusions = []
        self.drawn_person = None
    
    def add_exclusion(self, person):
        self.exclusions.append(person)
    
    def set_drawn_person(self, drawn_person):
        self.drawn_person = drawn_person
    
    def set_name(self, name):
        self.name = name
    
    def set_email(self, email):
        self.email = email

    def get_name(self):
        return self.name
    
    def get_email(self):
        return self.email

    def get_exclusions(self):
        return self.exclusions
    
    def get_drawn_person(self):
        return self.drawn_person