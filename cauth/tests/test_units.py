# Copyright (C) 2014 eNovance SAS <licensing@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from unittest import TestCase
from mock import patch, Mock, ANY
from M2Crypto import RSA, BIO

from cauth import auth

from cauth.utils.userdetails import Gerrit
from cauth.controllers import root, github
from cauth.model import db
from cauth.utils import common

from webtest import TestApp
from pecan import load_app
from webob.exc import HTTPUnauthorized

import base64
import crypt
import tempfile
import json
import os

import httmock
import urlparse


def raise_(ex):
    raise ex


class dummy_conf():
    def __init__(self):
        self.redmine = {'apikey': 'XXX',
                        'apihost': 'api-redmine.test.dom',
                        'apiurl': 'http://api-redmine.test.dom',
                        }
        self.gerrit = {'url': 'XXX',
                       'admin_user': 'admin',
                       'admin_password': 'wxcvbn',
                       'db_host': 'mysql.tests.dom',
                       'db_name': 'gerrit',
                       'db_user': 'gerrit',
                       'db_password': 'wxcvbn',
                       }
        self.app = {'priv_key_path': '/tmp/priv_key',
                    'cookie_domain': 'tests.dom',
                    'cookie_period': 3600,
                    'root': 'cauth.controllers.root.RootController',
                    'template_path': os.path.join(os.path.dirname(__file__),
                                                  '../templates'),
                    'modules': ['cauth'],
                    'debug': True,
                    }
        self.auth = {'ldap':
                     {'host': 'ldap://ldap.tests.dom',
                         'dn': 'cn=%(username)s,ou=Users,dc=tests,dc=dom',
                         'sn': 'sn',
                         'mail': 'mail', },
                     'github':
                     {'top_domain': 'tests.dom',
                      'auth_url': 'https://github.com/login/oauth/authorize',
                      'redirect_uri':
                      'http://tests.dom/auth/login/github/callback"',
                      'client_id': 'XXX',
                      'client_secret': 'YYY', },
                     'users':
                         {
                             "user1": {
                                 "lastname": "Demo user1",
                                 "mail": "user1@tests.dom",
                                 "password": crypt.crypt(
                                     "userpass", "$6$EFeaxATWohJ")
                             }
                         },
                     'localdb':
                         {
                             "managesf_url": "http://tests.dom",
                         },
                     }
        self.sqlalchemy = {'url': 'sqlite:///%s' % tempfile.mkstemp()[1],
                           'echo': False,
                           'encoding': 'utf-8',
                           }
        self.logout = {'gerrit': {'url': '/r/logout'}}
        self.logging = {'loggers':
                        {'root': {'level': 'INFO', 'handlers': ['console']},
                         'cauth': {'level': 'DEBUG', 'handlers': ['console']},
                         'py.warnings': {'handlers': ['console']},
                         '__force_dict__': True},
                        'handlers': {
                            'console': {'level': 'DEBUG',
                                        'class': 'logging.StreamHandler',
                                        'formatter': 'simple'}},
                        'formatters': {
                            'simple': {
                                'format': (
                                    '%(asctime)s %(levelname)-5.5s [%(name)s]'
                                    '[%(threadName)s] %(message)s')}
                            }
                        }


def redmine_create_user_mock(*args, **kwargs):
    assert 'data' in kwargs
    assert 'X-Redmine-API-Key' in kwargs['headers']
    return FakeResponse(200)


def gen_rsa_key():
    conf = dummy_conf()
    if not os.path.isfile(conf.app['priv_key_path']):
        key = RSA.gen_key(2048, 65537, callback=lambda x, y, z: None)
        memory = BIO.MemoryBuffer()
        key.save_key_bio(memory, cipher=None)
        p_key = memory.getvalue()
        file(conf.app['priv_key_path'], 'w').write(p_key)


class FunctionalTest(TestCase):
    def setUp(self):
        c = dummy_conf()
        gen_rsa_key()
        config = {'redmine': c.redmine,
                  'gerrit': c.gerrit,
                  'app': c.app,
                  'auth': c.auth,
                  'logout': c.logout,
                  'sqlalchemy': c.sqlalchemy}
        # deactivate loggin that polute test output
        # even nologcapture option of nose effetcs
        # 'logging': c.logging}
        self.app = TestApp(load_app(config))

    def tearDown(self):
        pass


class FakeResponse():
    def __init__(self, code, content=None, is_json=False):
        self.status_code = code
        self.content = content
        self._json = {}
        if is_json and content:
            self._json = json.loads(content)

    def json(self, *args, **kwargs):
        return self._json


class TestUserDetails(TestCase):
    @classmethod
    def setupClass(cls):
        cls.conf = dummy_conf()

    @classmethod
    def tearDownClass(cls):
        pass

    def gerrit_add_sshkeys_mock(self, *args, **kwargs):
        self.assertIn('data', kwargs)
        self.assertIn('auth', kwargs)
        self.key_amount_added += 1

    def gerrit_get_account_id_mock(self, *args, **kwargs):
        data = json.dumps({'_account_id': 42})
        # Simulate the garbage that occurs in live tests
        data = 'garb' + data
        return FakeResponse(200, data)

    def gerrit_get_account_id_mock2(self, *args, **kwargs):
        data = json.dumps({})
        # Simulate the garbage that occurs in live tests
        data = 'garb' + data
        return FakeResponse(200, data)

    def test_gerrit_install_ssh_keys(self):
        ger = Gerrit(self.conf)
        self.key_amount_added = 0
        keys = [{'key': 'k1'}, {'key': 'k2'}]
        with patch('cauth.utils.userdetails.requests') as r:
            r.post = self.gerrit_add_sshkeys_mock
            ger.install_sshkeys('john', keys)
        self.assertEqual(self.key_amount_added, len(keys))

    def test_gerrit_add_in_acc_external(self):
        class FakeDB():
            def __init__(self, success=True):
                self.success = success

            def cursor(self):
                return FakeCursor(self.success)

            def commit(self):
                pass

        class FakeCursor():
            def __init__(self, success):
                self.success = success

            def execute(self, sql):
                if not self.success:
                    raise Exception

        ger = Gerrit(self.conf)
        with patch('cauth.utils.userdetails.MySQLdb') as m:
            m.connect = lambda *args, **kwargs: FakeDB()
            ret = ger.add_in_acc_external(42, 'john')
        self.assertEqual(True, ret)
        with patch('cauth.utils.userdetails.MySQLdb') as m:
            m.connect = lambda *args, **kwargs: FakeDB(False)
            ret = ger.add_in_acc_external(42, 'john')
        self.assertEqual(False, ret)

    def test_create_gerrit_user(self):
        ger = Gerrit(self.conf)
        with patch('cauth.utils.userdetails.requests') as r:
            r.put = lambda *args, **kwargs: None
            r.get = self.gerrit_get_account_id_mock
            ger.add_in_acc_external = Mock()
            ger.create_gerrit_user('john', 'john@tests.dom', 'John Doe', [])
            self.assertEqual(True, ger.add_in_acc_external.called)
        with patch('cauth.utils.userdetails.requests') as r:
            r.put = lambda *args, **kwargs: None
            r.get = self.gerrit_get_account_id_mock2
            ger.add_in_acc_external = Mock()
            ger.create_gerrit_user('john', 'john@tests.dom', 'John Doe', [])
            self.assertEqual(False, ger.add_in_acc_external.called)


class TestControllerRoot(TestCase):
    @classmethod
    def setupClass(cls):
        cls.conf = dummy_conf()
        gen_rsa_key()
        root.conf = cls.conf

    @classmethod
    def tearDownClass(cls):
        pass

    def test_signature(self):
        self.assertIsNot(None, common.signature('data'))

    def test_pre_register_user(self):
        p = 'cauth.utils.userdetails.UserDetailsCreator.create_user'
        with patch(p) as cu:
            common.pre_register_user('john')
            cu.assert_called_once_with(
                'john',
                'john@%s' % self.conf.app['cookie_domain'],
                'User john',
                None)

    def test_create_ticket(self):
        with patch('cauth.utils.common.signature') as sign:
            sign.return_value = '123'
            self.assertEqual('a=arg1;b=arg2;sig=123',
                             common.create_ticket(a='arg1', b='arg2'))


class TestLoginController(TestCase):
    @classmethod
    def setupClass(cls):
        cls.conf = dummy_conf()
        root.conf = cls.conf

    @classmethod
    def tearDownClass(cls):
        pass

    def test_check_valid_user(self):
        ret = auth.check_static_user(self.conf, 'user1', 'userpass')
        self.assertIn('user1@tests.dom', ret)
        self.assertIn('Demo user1', ret)
        with patch('requests.get'):
            ret = auth.check_static_user(self.conf, 'user1', 'badpass')
            self.assertEqual(None, ret)

    def test_check_localdb_user(self):
        with patch('requests.get') as g:
            _response = {'username': 'les',
                         'fullname': 'Les Claypool',
                         'email': 'les@primus.com',
                         'sshkey': 'Jerry was a race car driver'}
            g.return_value = FakeResponse(200, json.dumps(_response), True)
            ret = auth.check_db_user(self.conf, 'les', 'Wynona')
            self.assertIn('Les Claypool', ret)
            self.assertIn('les@primus.com', ret)
            self.assertIn([{'key': 'Jerry was a race car driver'}, ], ret)
        with patch('requests.get') as g:
            g.return_value = FakeResponse(401, 'Unauthorized')
            ret = auth.check_db_user(self.conf, 'bootsy', 'collins')
            self.assertEqual(None, ret)


@httmock.urlmatch(netloc=r'(.*\.)?github\.com$')
def githubmock_request(url, request):
    users = {
        "user6": {"login": "user6",
                  "password": "userpass",
                  "email": "user6@tests.dom",
                  "name": "Demo user6",
                  "ssh_keys": "",
                  "code": "user6_code",
                  "token": "user6_token"}
    }

    headers = {'content-type': 'application/json'}

    # Handle a token request
    if request.method == 'POST':
        code = urlparse.parse_qs(url.query)['code'][0]
        for user in users:
            if users[user]['code'] == code:
                token = users[user]['token']
                break
        content = {"access_token": token}
    # Handle informations request
    else:
        u = None
        for user in users:
            auth_header = request.headers['Authorization']
            _token = users[user]['token']
            # handle oauth
            if _token in auth_header:
                u = user
                break
            # handle API key auth
            elif base64.b64encode(_token + ':x-oauth-basic') in auth_header:
                u = user
                break
        if not u:
            # user not found, do not authorize
            error_content = {u'message': u'Bad credentials'}

            return httmock.response(401, error_content)
        if 'keys' in url.path:
            content = {'key': users[u]['ssh_keys']}
        else:
            content = {'login': u,
                       'email': users[u]['email'],
                       'name': users[u]['name']}
    return httmock.response(200, content, headers, None, 5, request)


class TestPersonalAccessTokenGithubController(TestCase):
    @classmethod
    def setupClass(cls):
        cls.conf = dummy_conf()
        gen_rsa_key()
        github.conf = cls.conf

    @classmethod
    def tearDownClass(cls):
        pass

    def test_authenticate(self):
        with httmock.HTTMock(githubmock_request):
            common.setup_response = Mock()
            gc = github.PersonalAccessTokenGithubController()
            gc.organization_allowed = lambda token: True
            gc.index(back='/r/', token='user6_token')
            common.setup_response.assert_called_once_with(
                'user6', '/r/', 'user6@tests.dom', 'Demo user6', {'key': ''})

        with httmock.HTTMock(githubmock_request):
            gc = github.PersonalAccessTokenGithubController()
            gc.organization_allowed = lambda token: False
            self.assertRaises(HTTPUnauthorized,
                              gc.index, back='/r/', token='bad_token')

    @patch('requests.get')
    def test_organization_allowed(self, mocked_get):
        gc = github.PersonalAccessTokenGithubController()
        mocked_get.return_value.json.return_value = [{'login': 'acme'}]

        # allowed_organizations not set -> allowed
        self.assertEqual(True, gc.organization_allowed('token'))

        # allowed_organizations set empty -> allowed
        self.conf.auth['github']['allowed_organizations'] = ''
        self.assertEqual(True, gc.organization_allowed('token'))

        # allowed_organizations set, doesn't match token orgs -> not allowed
        self.conf.auth['github']['allowed_organizations'] = 'some,other'
        self.assertEqual(False, gc.organization_allowed('token'))
        mocked_get.assert_called_with(
            'https://api.github.com/user/orgs',
            auth=ANY)

        # allowed_organizations set, doesn't match token orgs -> not allowed
        self.conf.auth['github']['allowed_organizations'] = 'some,other,acme'
        self.assertEqual(True, gc.organization_allowed('token'))
        mocked_get.assert_called_with(
            'https://api.github.com/user/orgs',
            auth=ANY)


class TestGithubController(TestCase):
    @classmethod
    def setupClass(cls):
        cls.conf = dummy_conf()
        gen_rsa_key()
        github.conf = cls.conf

    @classmethod
    def tearDownClass(cls):
        pass

    def test_get_access_token(self):
        with httmock.HTTMock(githubmock_request):
            gc = github.GithubController()
            self.assertEqual('user6_token',
                             gc.get_access_token('user6_code'))

    def test_callback(self):
        with httmock.HTTMock(githubmock_request):
            db.get_url = Mock(return_value='/r/')
            common.setup_response = Mock()
            gc = github.GithubController()
            gc.organization_allowed = lambda login: True
            gc.callback(state='stateXYZ', code='user6_code')
            common.setup_response.assert_called_once_with(
                'user6', '/r/', 'user6@tests.dom', 'Demo user6', {'key': ''})

        with httmock.HTTMock(githubmock_request):
            db.get_url = Mock(return_value='/r/')
            gc = github.GithubController()
            gc.organization_allowed = lambda login: False
            self.assertRaises(HTTPUnauthorized,
                              gc.callback, state='stateXYZ', code='user6_code')

    @patch('requests.get')
    def test_organization_allowed(self, mocked_get):
        gc = github.GithubController()
        mocked_get.return_value.json.return_value = [{'login': 'acme'}]

        # allowed_organizations not set -> allowed
        self.assertEqual(True, gc.organization_allowed('token'))

        # allowed_organizations set empty -> allowed
        self.conf.auth['github']['allowed_organizations'] = ''
        self.assertEqual(True, gc.organization_allowed('token'))

        # allowed_organizations set, doesn't match token orgs -> not allowed
        self.conf.auth['github']['allowed_organizations'] = 'some,other'
        self.assertEqual(False, gc.organization_allowed('token'))
        mocked_get.assert_called_with(
            'https://api.github.com/user/orgs',
            headers={'Authorization': 'token token'})

        # allowed_organizations set, doesn't match token orgs -> not allowed
        self.conf.auth['github']['allowed_organizations'] = 'some,other,acme'
        self.assertEqual(True, gc.organization_allowed('token'))
        mocked_get.assert_called_with(
            'https://api.github.com/user/orgs',
            headers={'Authorization': 'token token'})


class TestCauthApp(FunctionalTest):
    def test_get_login(self):
        response = self.app.get('/login', params={'back': 'r/'})
        self.assertGreater(response.body.find('value="r/"'), 0)
        self.assertGreater(response.body.find('/auth/login/github?back=r/'), 0)
        self.assertEqual(response.status_int, 200)

    def test_post_login(self):
        # Ldap and Gitub Oauth backend are mocked automatically
        # if the domain is tests.dom
        with patch('cauth.utils.userdetails.requests'):
            response = self.app.post('/login', params={'username': 'user1',
                                                       'password': 'userpass',
                                                       'back': 'r/'})
        self.assertEqual(response.status_int, 303)
        self.assertEqual('http://localhost/r/', response.headers['Location'])
        self.assertIn('Set-Cookie', response.headers)
        with patch('requests.get'):
            # baduser is not known from the mocked backend
            with patch('cauth.utils.userdetails'):
                response = self.app.post('/login',
                                         params={'username': 'baduser',
                                                 'password': 'userpass',
                                                 'back': 'r/'},
                                         status="*")
            self.assertEqual(response.status_int, 401)

            # Try with no creds
            with patch('cauth.utils.userdetails'):
                response = self.app.post('/login', params={'back': 'r/'},
                                         status="*")
            self.assertEqual(response.status_int, 401)

    def test_github_login(self):
        with httmock.HTTMock(githubmock_request):
            with patch('cauth.utils.userdetails'):
                response = self.app.get('/login/github/index',
                                        params={'username': 'user6',
                                                'back': 'r/',
                                                'password': 'userpass'})
                self.assertEqual(response.status_int, 302)
                parsed = urlparse.urlparse(response.headers['Location'])
                parsed_qs = urlparse.parse_qs(parsed.query)
                self.assertEqual('https', parsed.scheme)
                self.assertEqual('github.com', parsed.netloc)
                self.assertEqual('/login/oauth/authorize', parsed.path)
                self.assertEqual(
                    ['user:email, read:public_key, read:org'],
                    parsed_qs.get('scope'))
                self.assertEqual(
                    ['http://tests.dom/auth/login/github/callback"'],
                    parsed_qs.get('redirect_uri'))

    def test_get_logout(self):
        # Ensure client SSO cookie content is deleted
        response = self.app.get('/logout')
        self.assertEqual(response.status_int, 200)
        self.assertTrue('auth_pubtkt=;' in response.headers['Set-Cookie'])
        self.assertGreater(response.body.find(root.LOGOUT_MSG), 0)
