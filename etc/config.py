#
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

# Pecan Application Configurations
app = {
    'root': 'cauth.controllers.root.RootController',
    'modules': ['cauth'],
    'static_root': '%(confdir)s/public',
    'template_path': '%(confdir)s/cauth/templates',
    'priv_key_path': '/srv/cauth_keys/privkey.pem',
    'cookie_domain': 'tests.dom',
    'debug': False,
    'cookie_period': 43200
}

logging = {
    'loggers': {
        'cauth': {'level': 'DEBUG',
                  'handlers': ['file_handler']},
        'pysflib': {'level': 'DEBUG',
                    'handlers': ['file_handler']},
        '__force_dict__': True
    },
    'handlers': {
        'file_handler': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'simple',
            'filename': '/var/log/cauth/cauth.log',
        }
    },
    'formatters': {
        'simple': {
            'format': ('%(asctime)s %(levelname)-5.5s [%(name)s]'
                       '[%(threadName)s] %(message)s')
        }
    }
}

# Authorization configurations
auth = {
    'ldap': {
        'host': 'my.ldap.url',
        'dn': 'uid=%(username)s,ou=test,dc=corp',
        'sn': 'sn_attribute',
        'mail': 'ldap_account_mail_attribute',
    },
    'github': {
        'top_domain': 'tests.dom',
        'auth_url':  'https://github.com/login/oauth/authorize',
        'redirect_uri': 'https://github/redirect/url',
        'client_id': 'your_github_app_id',
        'client_secret': 'your_github_app_secret',
        'allowed_organizations': 'your_allowed_organizations'
    },
    'localdb': {
        'managesf_url': 'https://tests.dom',
    },
    'users': {
        "user1": {
            "lastname": "example user",
            "mail": "user@tests.dom",
            "password": "password",
        },
    }
}

logout = {
    'services': ['redmine', 'gerrit', 'cauth'],
    'gerrit': {
        'url': '/r/logout'
    },
    'redmine': {
        'url': '/redmine/logout'
    }
}

sqlalchemy = {
    'url': 'sqlite:////var/lib/cauth/state_mapping.db',
    'echo': True,
    'encoding': 'utf-8'
}

redmine = {
    'apihost': 'redmine_api_host',
    'apiurl': '',
    'apikey': '',
}

gerrit = {
    'url': 'http://gerrit.url',
    'admin_user': 'admin',
    'admin_password': 'password',
    'db_host': 'gerrit_mysql_address',
    'db_name': 'gerrit_mysql_db',
    'db_user': 'gerrit_mysql_username',
    'db_password': 'gerrit_sql_pwd'
}
