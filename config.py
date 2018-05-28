# coding=utf-8

import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'wibbly wobbly timey wimey'

    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True

    SCHEDULER_API_ENABLED = True
    # 任务调度不再使用apscheduler，现在只用于crontab的校验
    # SCHEDULER_JOBSTORES = {
    #     'default': SQLAlchemyJobStore(url='sqlite:///' + os.path.join(basedir, 'jobs.sqlite'))
    # }
    # SCHEDULER_EXECUTORS = {
    #     'default': {'type': 'threadpool', 'max_workers': 10}
    # }

    POLARIS_ADMIN = os.environ.get('POLARIS_ADMIN') or 'earrow.liu@gmail.com'
    POLARIS_RECORDS_PER_PAGE = 20
    POLARIS_TASKS_PER_PAGE = 20
    POLARIS_PROJECTS_PER_PAGE = 20
    POLARIS_SERVERS_PER_PAGE = 10


class DevelopmentConfig(Config):
    DEBUG = False

    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'data-dev.sqlite')

    JENKINS_HOST = ''
    JENKINS_USERNAME = ''
    JENKINS_PASSWORD = ''


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    pass


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}