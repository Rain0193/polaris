# coding=utf-8

from app import db, app
from app.models import User, Role, Task, Result, Project, Record, Manual, EmailTemplate
from flask_script import Manager, Shell, Server

manager = Manager(app)


def make_shell_context():
    return dict(app=app, db=db, User=User, Role=Role, Task=Task, Result=Result, Project=Project, Record=Record,
                Manual=Manual, EmailTemplate=EmailTemplate)


manager.add_command('shell', Shell(make_context=make_shell_context))
manager.add_command('runserver', Server(host='0.0.0.0'))

if __name__ == '__main__':
    manager.run()
