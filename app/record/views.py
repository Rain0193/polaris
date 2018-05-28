# coding=utf-8

import json
import logging

import redis
from flask import render_template, url_for, request, jsonify, current_app, abort
from flask_login import current_user

from . import record
from .. import db, jenkins
from ..models import Record, Project, Task, Result

logger = logging.getLogger('polaris.record')
r = redis.Redis('localhost')


@record.route('/')
def record_list():
    project_id = request.args.get('project_id', type=int)
    task_id = request.args.get('task_id', type=int)

    p = Project.query.get(project_id)
    if current_user not in p.testers and current_user not in p.editors:
        abort(403)

    logger.debug('get {}'.format(url_for('.record_list', project_id=project_id, task_id=task_id)))

    page = request.args.get('page', 1, type=int)

    if task_id != -1:
        pagination = Record.query.filter_by(project_id=project_id, task_id=task_id).order_by(
            Record.timestamp.desc()).paginate(page, per_page=current_app.config['POLARIS_RECORDS_PER_PAGE'],
                                              error_out=False)
    else:
        pagination = Record.query.filter_by(project_id=project_id).order_by(
            Record.timestamp.desc()).paginate(page, per_page=current_app.config['POLARIS_RECORDS_PER_PAGE'],
                                              error_out=False)

    test_records = pagination.items
    logger.debug('length of records: {}'.format(len(test_records)))
    return render_template('record/records.html', records=test_records, pagination=pagination, project_id=project_id,
                           task_id=task_id)


@record.route('/<record_id>/console/')
def console(record_id):
    test_record = Record.query.get(record_id)
    p = test_record.project
    if current_user not in p.testers and current_user not in p.editors:
        abort(403)

    console_output = jenkins._server.get_build_console_output(test_record.task.name, test_record.build_number).replace(
        '\r', '').replace('\n', '<br>')
    r.set('console_output:{}:{}'.format(test_record.task.name, test_record.build_number), console_output)

    return render_template('record/console.html', ret=console_output, task_name=test_record.task.name,
                           build_number=test_record.build_number)


@record.route('/console_check/')
def console_check():
    logger.debug('get {}'.format(url_for('.console_check')))

    task_name = request.args.get('task_name')
    build_number = int(request.args.get('build_number'))

    console_output_cache = r.get('console_output:{}:{}'.format(task_name, build_number)).decode('utf-8')
    console_output = jenkins._server.get_build_console_output(task_name, build_number).replace('\r', '').replace('\n',
                                                                                                                 '<br>')
    r.set('console_output:{}:{}'.format(task_name, build_number), console_output)

    build_info = jenkins._server.get_build_info(task_name, build_number)
    if build_info['result']:
        end = True
    else:
        end = False
    return jsonify(ret=console_output.lstrip(console_output_cache), end=end)


@record.route('/<record_id>/analysis/')
def analysis(record_id):
    """单次执行记录结果统计。"""
    test_record = Record.query.get(record_id)
    p = test_record.project
    if current_user not in p.testers and current_user not in p.editors:
        abort(403)

    if test_record.result:
        if test_record.result.tests:
            ret = {
                'tests': test_record.result.tests,
                'errors': test_record.result.errors,
                'failures': test_record.result.failures,
                'skip': test_record.result.skip
            }
        else:
            ret = '结果文件未配置或不存在'
    else:
        ret = '请等待测试结束后再查看'

    return render_template('record/analysis.html', ret=ret)


@record.route('/report_result', methods=['POST'])
def report_result():
    """接收测试结果数据上报。"""
    logger.debug(f'get result report: {request.get_data()}')

    result = json.loads(request.get_data().decode('utf-8'))
    r.set(f'result:tests:{result["project_name"]}:{result["task_name"]}', result['tests'])
    r.set(f'result:errors:{result["project_name"]}:{result["task_name"]}', result['errors'])
    r.set(f'result:failures:{result["project_name"]}:{result["task_name"]}', result['failures'])
    r.set(f'result:skip:{result["project_name"]}:{result["task_name"]}', result['skip'])

    return jsonify(status=0, msg='ok')


@record.route('/check_state/')
def check_state():
    """检查执行状态，通过ajax调用。"""
    logger.debug('get {}'.format(url_for('.check_state')))

    state = 0  # 是否有测试任务已经执行结束，0：没有，1：有。若有结束的任务，则测试记录页面需要自动刷新
    p = Project.query.get(int(request.args.get('project_id')))

    tasks = Task.query.filter_by(project=p).all()
    for task in tasks:
        job_info = jenkins._server.get_job_info(task.name)
        builds = job_info['builds'][::-1]
        for build in builds:
            build_number = build['number']

            # 根据jenkins的构建记录查询数据库中的记录
            rcd = Record.query.filter_by(task=task).filter_by(build_number=build_number).first()

            # 数据库中没有该记录，则添加进去
            if rcd is None:
                rcd = Record(user=current_user, project=p, task=task, state=0, version='9999',
                             build_number=build_number)
                db.session.add(rcd)
                db.session.commit()

            if rcd.state == -2:
                try:
                    build_info = jenkins._server.get_build_info(rcd.task.name, rcd.build_number)
                    rcd.state = 0
                    db.session.commit()
                except jenkins.NotFoundException:
                    pass

            # 查询记录是否已经执行完毕
            if rcd.state == 0:
                build_info = jenkins._server.get_build_info(rcd.task.name, rcd.build_number)
                if build_info['result']:
                    console_output = jenkins._server.get_build_console_output(rcd.task.name, rcd.build_number)

                    test_result = Result(record=rcd, status=0 if build_info['result'] == 'SUCCESS' else -1,
                                         cmd_line=console_output, tests=0, errors=0, failures=0, skip=0)

                    tests = f'result:tests:{rcd.project.name}:{rcd.task.nickname}'
                    errors = f'result:errors:{rcd.project.name}:{rcd.task.nickname}'
                    failures = f'result:failures:{rcd.project.name}:{rcd.task.nickname}'
                    skip = f'result:skip:{rcd.project.name}:{rcd.task.nickname}'

                    if r.exists(tests):
                        logger.debug(f'get rest result')
                        test_result.tests += int(r.get(tests))
                        test_result.errors += int(r.get(errors))
                        test_result.failures += int(r.get(failures))
                        test_result.skip += int(r.get(skip))

                        r.delete(tests, errors, failures, skip)

                    db.session.add(test_result)

                    if build_info['result'] == 'SUCCESS':
                        logger.debug('{} success'.format(rcd))
                        rcd.state = 1
                    else:
                        logger.debug('{} fail'.format(rcd))
                        rcd.state = -1
                    rcd.result = test_result
                    db.session.commit()

                    state = 1

    return jsonify(state=state)


@record.route('/do_test')
def do_test():
    """执行测试接口，通过ajax调用。"""
    project_id = request.args.get('project_id', type=int)
    task_id = request.args.get('task_id', type=int)
    version = request.args.get('version')
    logger.debug(f'get {url_for(".do_test", project_id=project_id, task_id=task_id, version=version)}')

    p = Project.query.get(project_id)
    t = Task.query.get(task_id)

    if current_user not in p.testers and current_user not in p.editors:
        return jsonify(state='no_permission')

    build_number = jenkins._server.get_job_info(t.name)['nextBuildNumber']

    if not jenkins._server.get_node_info(p.server.host)['offline']:
        # 测试服务器在线
        if Record.query.filter_by(task=t, state=0).first() or Record.query.filter_by(task=t, state=-2).first():
            # 该任务正在执行中
            return jsonify(state='busy')

        test_record = Record(user=current_user, project=p, task=t, state=0, version=version, build_number=build_number)
        db.session.add(test_record)
        db.session.commit()

        jenkins._server.build_job(t.name)
        logger.debug('testing {} of {}'.format(t, p))
        return jsonify(state='success')
    else:
        # 测试服务器离线
        logger.warning(f'{t} connect server tiemout')

        if not Record.query.filter_by(task=t, state=-2).first():
            test_record = Record(user=current_user, project=p, task=t, state=-2, version=version,
                                 build_number=build_number)
            db.session.add(test_record)
            db.session.commit()
            return jsonify(state='timeout')
        else:
            return jsonify(state='wait')