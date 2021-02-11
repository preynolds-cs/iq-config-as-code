#!/usr/bin/env python3

#
# Copyright 2019-Present Sonatype Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import argparse
import json

import requests

iq_session = requests.Session
iq_url, iq_auth, debug = "", "", False
categories, organizations, applications, ldap_connections = [], [], [], []
roleType = ['USER', 'GROUP']


def get_arguments():
    global iq_url, iq_session, iq_auth, debug
    parser = argparse.ArgumentParser(description='This script enables you to configure IQ Server from JSON\
     data, thus supporting the config-as-code requirement of Sonatype customers')
    parser.add_argument('-u', '--url', help='', default="http://localhost:8070", required=False)
    parser.add_argument('-a', '--auth', help='', default="admin:admin123", required=False)
    parser.add_argument('-f', '--file_name', default="conf/configuration.json", required=True)
    parser.add_argument('-d', '--debug', default=False, required=False)

    args = vars(parser.parse_args())
    iq_url = args["url"]
    credentials = args["auth"].split(":")
    debug = args["debug"]
    iq_session = requests.Session()
    iq_session.cookies.set('CLM-CSRF-TOKEN', 'api')
    iq_session.headers = {'X-CSRF-TOKEN': 'api'}
    # load user credentials, recommended to use admin account to avoid on-boarding errors.
    iq_auth = requests.auth.HTTPBasicAuth(credentials[0], credentials[1])
    iq_session.auth = iq_auth
    return args


def main():
    # grab defaults or args passed into script.
    args = get_arguments()
    file_name = args["file_name"]

    # store current applications, categories, and organizations
    set_categories()
    set_organizations()
    set_applications()

    with open(file_name) as json_file:
        config = json.load(json_file)

    # Admin level configuration and integrations
    nexus_administration()

    # ROOT level configuration
    root_configuration()
    data = {}

    # Iterate over the Organisations
    if organizations is not None:
        orgs = []
        # loops through config data
        for org in organizations:
            # Apply Organisation configuration
            org_conf = {}
            org_conf = org_configuration(org)
            org_apps = []
            for app in applications:
                if app['organizationId'] == org['id']:
                    org_apps.append(app_configuration(app))
            org_conf['applications'] = org_apps
            orgs.append(org_conf)
        data['organizations'] = orgs
        persist_data(data, 'scrape/orgs-apps-conf.json')


def nexus_administration():

    systemConf = {}
    # Parses and applies all the 'administrative' configuration for Nexus IQ
    systemConf['users'] = persist_users()
    systemConf['custom_roles'] = persist_roles()
    systemConf['ldap_connections'] = persist_ldap_instances()
    systemConf['email_server'] = persist_email_server_connection()
    systemConf['proxy'] = persist_proxy()
    systemConf['webhooks'] = persist_webhooks()
    systemConf['system_notice'] = persist_system_notice()
    systemConf['success_metrics'] = persist_success_metrics()
    systemConf['automatic_applications'] = persist_auto_applications()
    systemConf['source_control'] = persist_automatic_scc()
    systemConf['success_metrics_reports'] = persist_success_metrics_reports()
    persist_data(systemConf, 'scrape/system-conf.json')


def root_configuration():
    rootOrgConf = {}
    # Parses and applies all of the ROOT Org configuration
    rootOrgConf['application_categories'] = persist_application_categories()
    rootOrgConf['grandfathering'] = persist_grandfathering()
    rootOrgConf['continuous_monitoring'] = persist_continuous_monitoring()
    rootOrgConf['proprietary_components'] = persist_proprietary_components()
    rootOrgConf['component_labels'] = persist_component_labels()
    rootOrgConf['license_threat_groups'] = persist_license_threat_groups()
    rootOrgConf['data_purging'] = persist_data_purging()
    rootOrgConf['source_control'] = persist_source_control()
    rootOrgConf['access'] = persist_access()
    persist_data(rootOrgConf, 'scrape/root-org-conf.json')

def process_orgs():
    url = f'{iq_url}/api/v2/organizations'
    orgs = get_url(url)
    for org in orgs['organizations']:
        x = 1

    return None

def org_configuration(org):
    orgconf = {}
    # Parses and applies all of the child Org configuration
    orgconf['grandfathering'] = persist_grandfathering(org['id'])
    orgconf['continuous_monitoring_stage'] = persist_continuous_monitoring(org['id'])
    orgconf['source_control'] = persist_source_control(org['id'])
    orgconf['data_purging'] = persist_data_purging(org['id'])
    orgconf['proprietary_components'] = persist_proprietary_components(org['id'])
    orgconf['application_categories'] = persist_application_categories(org['id'])
    orgconf['component_labels'] = persist_component_labels(org['id'])
    orgconf['license_threat_groups'] = persist_license_threat_groups(org['id'])
    orgconf['access'] = persist_access(org['id'])
    orgconf['name'] = org['name']
    persist_data(orgconf, f'scrape/{get_organization_name(org["id"])}-config.json')
    return orgconf


def app_configuration(app):

    app_conf = {}
    # Parses and applies all of the application configuration
    app_conf['name'] = app['name']
    app_conf['grandfathering'] = persist_grandfathering(app=app['publicId'])
    app_conf['continuous_monitoring_stage'] = persist_continuous_monitoring(app=app['publicId'])
    app_conf['proprietary_components'] = persist_proprietary_components(app=app['publicId'])
    app_conf['component_labels'] = persist_component_labels(app=app['publicId'])
    app_conf['source_control'] = persist_source_control(app=app['id'])
    app_conf['publicId'] = app['publicId']
    app_conf['applicationTags'] = check_categories(app['applicationTags'])
    app_conf['access'] = persist_access(app['id'])
    # persist_data(app_conf, f'scrape/{app["name"]}-config.json')
    return app_conf

def print_debug(c):
    # testing json output to console
    if debug:
        print(json.dumps(c, indent=4))


def handle_resp(resp, root=""):
    # normalize api call responses
    if resp.status_code != 200:
        print(resp.text)
        return None
    node = resp.json()

    if root in node:
        node = node[root]
    if node is None or len(node) == 0:
        return None
    return node


def get_url(url, root=""):
    # common get call
    resp = iq_session.get(url, auth=iq_auth)
    return handle_resp(resp, root)


def post_url(url, params, root=""):
    # common post call
    resp = iq_session.post(url, json=params, auth=iq_auth)
    return handle_resp(resp, root)


def put_url(url, params, root=""):
    # common put call
    resp = iq_session.put(url, json=params, auth=iq_auth)
    return handle_resp(resp, root)


def delete_url(url, params, root=""):
    # common put call
    resp = iq_session.delete(url, json=params, auth=iq_auth)
    return handle_resp(resp, root)


def org_or_app(org, app):
    if app:
        return f'application/{app}'
    if org is None:
        org = 'ROOT_ORGANIZATION_ID'
    return f'organization/{org}'


def orgs_or_apps(org, app):
    if app:
        return f'applications/{app}'
    if org is None:
        org = 'ROOT_ORGANIZATION_ID'
    return f'organizations/{org}'


# --------------------------------------------------------------------------


def set_applications():
    global applications
    url = f'{iq_url}/api/v2/applications'
    applications = get_url(url, "applications")


def set_organizations():
    global organizations
    url = f'{iq_url}/api/v2/organizations'
    organizations = get_url(url, "organizations")


def set_categories():
    global categories
    # using categories from root organization.
    url = f'{iq_url}/api/v2/applicationCategories/organization/ROOT_ORGANIZATION_ID'
    categories = get_url(url)


def check_application(new_app):
    # name is required, default to PublicId
    if not new_app['name']:
        new_app['name'] = new_app['publicId']

    # Look to see if new app already exists
    for app in applications:
        if app['publicId'] == new_app['publicId']:
            return app
    return None


def get_organization_id(name):
    ret = None
    for org in organizations:
        if name in org['name']:
            ret = org['id']
            break
    return ret

def get_organization_name(id):
    ret = None
    for org in organizations:
        if id in org['id']:
            ret = org['name']
            break
    return ret


def check_ldap_connection(name):
    ret = ''
    for connection in ldap_connections:
        if name in connection['name']:
            ret = connection['id']
    if len(ret) == 0:
        ret = add_ldap_connection(name)
    if len(ret) > 0:
        return ret
    else:
        return None


def check_categories(app_tags):
    # If the application category does not exist, it will be added to the root organisation by default, by design.
    ret = []
    for tag in app_tags:
        tag_ = check_category(tag)
        if tag_ is not None:
            ret.append(tag_)
    return ret


def check_category(ac):
    ret = ''
    if len(ac) == 0:
        return None
    for c in categories:
        if ac['tagId'] == c['id']:
            ret = c['name']
            break
    if len(ret) > 0:
        return {'name': ret}
    return None

def category_exists(ac):
    ret = ''
    if len(ac) == 0:
        return None
    for c in categories:
        if ac['id'] == c['id']:
            ret = c['name']
            break
    if len(ret) > 0:
        return {'name': ret}
    return None

def check_roles(name, roles):
    ret = ''
    if len(name) == 0:
        return None
    for role in roles:
        if name in role['name']:
            ret = role['id']
            break
    if len(ret) > 0:
        return {'tagId': ret}
    print(f"Role {name} is not available within Nexus IQ")
    return None


def check_user_or_group(user_or_group):
    if len(user_or_group) == 0:
        return None
    if (user_or_group.upper() == "GROUP") or (user_or_group.upper() == "USER"):
        return user_or_group.upper()

    print(f"User type '{user_or_group}' does not exist! 'USER' or 'GROUP' are the valid types.")
    return None



def add_ldap_connection(ldap_conn_name):
    data = {"name": ldap_conn_name}
    url = f'{iq_url}/rest/config/ldap'
    resp = post_url(url, data)
    if resp is not None:
        ldap_connections.append(resp)
        print(f"Created LDAP connection: {ldap_conn_name}")
        return resp['id']
    return ''


# Apply roles to the endpoint identified within the URL
def apply_role(url, role_id, user_or_group_name, role_type):
    data = {
        "memberMappings": [
            {
                "roleId": role_id,
                "members": [
                    {
                        "type": role_type,
                        "userOrGroupName": user_or_group_name
                    }
                ]
            }
        ]
    }
    put_url(url, data)
    print("Applied RBAC data:")
    print_debug(data)


def persist_access(org='ROOT_ORGANIZATION_ID', app=None):
    url = f'{iq_url}/api/v2/{orgs_or_apps(org, app)}/roleMembers'
    roles = find_available_roles()

    # for role in roles:
    #     url = f'{iq_url}/rest/membershipMapping/organization/{org}/role/{role["id"]}'


    # for acc in access:
    #     # Apply the roles to the application
    #     role = acc['role']
    #     role_id = check_roles(role, iq_roles)
    #     user_or_group_name = acc['user_or_group_name']
    #     role_type = acc['role_type']
    #
    #     # Now apply the roles for the new applications
    #     # if (check_user(user_or_group_name, users, role_type) is not None) and \
    #     if (check_user_or_group(role_type) is not None) and (role_id is not None):
    #         # Validation completed, apply the roles!
    #         # No return payload with a 204 PUT response!
    #         apply_role(url, role_id['tagId'], user_or_group_name, role_type)
    #         print(f"to '{role}' for '{role_type}:{user_or_group_name}' to '{entity['name']}'")
    #     else:
    #         print(f"Unable to apply '{role}' for '{role_type}:{user_or_group_name}' to '{entity['name']}'")

    return []



def persist_auto_applications():
    url = f'{iq_url}/rest/config/automaticApplications'
    data = get_url(url)
    for org in organizations:
        if org['id'] == data['parentOrganizationId']:
            data['parentOrganizationId'] = org['name']
            break
    # persist_data(data, 'scrape/system-auto_applications.json')
    print_debug(data)
    return data


def persist_grandfathering(org='ROOT_ORGANIZATION_ID', app=None):

    url = f'{iq_url}/rest/policyViolationGrandfathering/{org_or_app(org, app)}'

    data = get_url(url)
    # if app is not None:
    #     persist_data(data, f'scrape/{app["name"]}-grandfathering.json')
    # elif org is not None:
    #     persist_data(data, f'scrape/{get_organization_name(org)}-grandfathering.json')
    print_debug(data)
    return data


def persist_webhooks():
    url = f'{iq_url}/rest/config/webhook'
    data = []
    webhooks = get_url(url)
    if not (webhooks is None):
        for webhook in webhooks:
            webhook['id'] = None
            data.append(webhook)

    # persist_data(data, 'scrape/system-webhooks.json')
    print_debug(data)
    return data


def persist_proxy():
    # This API applies the config regardless of whether the proxy is already configured.
    url = f'{iq_url}/api/v2/config/httpProxyServer'
    data = get_url(url)
    # persist_data(data, 'scrape/system-proxy.json')
    print_debug(data)
    return data


def persist_source_control(org='ROOT_ORGANIZATION_ID', app=None):
    url = f'{iq_url}/api/v2/sourceControl/{org_or_app(org, app)}'
    # This API applies the config regardless of whether the proxy is already configured.
    data = get_url(url)
    if data is not None:
        data.pop('id')
        data.pop('ownerId')
    # if app is not None:
    #     persist_data(data, f'scrape/{app["name"]}-source_control.json')
    # elif org is not None:
    #     persist_data(data, f'scrape/{get_organization_name(org)}-source_control.json')
    print_debug(data)
    return data


def persist_success_metrics():
    url = f'{iq_url}/rest/successMetrics'
    # This API applies the config regardless of whether the proxy is already configured.
    data = get_url(url)
    # persist_data(data, 'scrape/system-success_metrics.json')
    print_debug(data)
    return data


def persist_success_metrics_reports():
    url = f'{iq_url}/rest/successMetrics/report'
    # This API applies the config regardless of whether the proxy is already configured.
    data = get_url(url)
    for sm in data:
        sm.pop('id')
        sm.pop('scope')
        sm['scope'] = {}

    # persist_data(data, 'scrape/system-success_metrics_reports.json')
    print_debug(data)
    return data


def persist_automatic_scc():
    url = f'{iq_url}/rest/config/automaticScmConfiguration'
    # This API applies the config regardless of whether the proxy is already configured.
    data = get_url(url)
    # persist_data(data, 'scrape/system-automatic_scc.json')
    print_debug(data)
    return data


def persist_proprietary_components(org='ROOT_ORGANIZATION_ID', app=None):
    url = f'{iq_url}/rest/proprietary/{org_or_app(org, app)}'
    # This API applies the config regardless of whether the proxy is already configured.
    pcs = get_url(url)
    pcs = pcs['proprietaryConfigByOwners']
    pcs2 = []
    for pc in pcs:
        data = pc['proprietaryConfig']
        data['id'] = None
        data.pop('ownerId')
        pcs2.append(data)
        # if app is not None:
        #     persist_data(data, f'scrape/{app["name"]}-proprietary_component.json')
        # elif org is not None:
        #     persist_data(data, f'scrape/{get_organization_name(org)}-proprietary_component.json')
        print_debug(data)
    return pcs2

def persist_roles():
    url = f'{iq_url}/rest/security/roles'
    data = get_url(url)
    for element in data:
        element.pop('id', None)
    # persist_data(data, 'scrape/system_roles.json')
    print_debug(data)
    return data


def persist_continuous_monitoring(org='ROOT_ORGANIZATION_ID', app=None):
    url = f'{iq_url}/rest/policyMonitoring/{org_or_app(org, app)}'
    data = get_url(url)
    if data is not None:
        data.pop('id')
        data.pop('ownerId')
    # if app is not None:
    #     persist_data(data, f'scrape/{app["name"]}-continuous_monitoring.json')
    # elif org is not None:
    #     persist_data(data, f'scrape/{get_organization_name(org)}-continuous_monitoring.json')
    print_debug(data)
    return data


def persist_data_purging(org='ROOT_ORGANIZATION_ID'):
    url = f'{iq_url}/api/v2/dataRetentionPolicies/organizations/{org}'
    data = get_url(url)
    # persist_data(data, f'scrape/{get_organization_name(org)}-data_purging.json')
    print_debug(data)
    return data


def persist_application_categories(org='ROOT_ORGANIZATION_ID'):
    url = f'{iq_url}/api/v2/applicationCategories/organization/{org}'
    data = get_url(url)
    if data is not None:
        for ac in data:
            if category_exists(ac) is None:
                categories.append(ac.copy())
            ac.pop('id')
            ac.pop('organizationId')

    print_debug(data)
    # persist_data(data, f'scrape/{get_organization_name(org)}-application_categories.json')
    return data



def persist_component_labels(org='ROOT_ORGANIZATION_ID', app=None):
    url = f'{iq_url}/api/v2/labels/{org_or_app(org, app)}'
    data = get_url(url)
    if data is not None:
        for label in data:
            label.pop('id')
            label.pop('ownerId')
    print_debug(data)
    # persist_data(data, f'scrape/{get_organization_name(org)}-component_labels.json')
    return data


def persist_license_threat_groups(org='ROOT_ORGANIZATION_ID'):
    url = f'{iq_url}/rest/licenseThreatGroup/organization/{org}'
    data = get_url(url)
    if data is not None:
        for ltg in data:
            ltg.pop('id')
            ltg.pop('ownerId')
            ltg.pop('nameLowercaseNoWhitespace')
    print_debug(data)
    # persist_data(data, f'scrape/{get_organization_name(org)}-license_threat_groups.json')
    return data


def persist_ldap_instances():
    try:
        url = f'{iq_url}/rest/config/ldap'
        data = []
        # Connection is created above, so it is expected in the list of connections
        conns = get_url(url)
        if not (conns is None):
            for conn in conns:
                data.append(parse_ldap_connection(conn))

        print_debug(data)
        # persist_data(data, 'scrape/system-ldap_connections.json')
        return data

    except KeyError as err:
        print("Error parsing: {0}".format(err))


def persist_email_server_connection():
    url = f'{iq_url}/api/v2/config/mail'
    data = get_url(url)
    # persist_data(data, 'scrape/system_email.json')
    print_debug(data)
    return data


def persist_users():
    url = f'{iq_url}/rest/user'
    data = get_url(url)
    for element in data:
        element.pop('id', None)
        element.pop('usernameLowercase', None)
    # persist_data(data, "scrape/system_users.json")
    print_debug(data)
    return data


def persist_system_notice():
    url = f'{iq_url}/rest/config/systemNotice'
    data = get_url(url)
    # persist_data(data, 'scrape/system-system_notice.json')
    print_debug(data)
    return data


def parse_ldap_connection(conn):
    data = {'name': conn['name']}
    url = f'{iq_url}/rest/config/ldap/{conn["id"]}/connection'
    response = get_url(url)
    response.pop('id', None)
    serverId = response.pop('serverId', None)

    data['connection'] = response
    url = f'{iq_url}/rest/config/ldap/{serverId}/userMapping'
    response = get_url(url)
    response.pop('id', None)
    response.pop('serverId', None)

    data['mappings'] = response
    print("Mapped LDAP connection:")
    return data


def find_available_roles():
    url = f'{iq_url}/api/v2/applications/roles'
    resp = get_url(url)
    if resp is not None:
        return resp['roles']
    return ''


def name_available(name):
    for app in applications:
        if app['name'] == name:
            return False
    return True


# Write the data to a file...
def persist_data(data, filename):
    with open(filename, 'w') as outfile:
        json.dump(data, outfile, indent=2)
    print(f'Persisted data to {filename}')


# --------------------------------------------------------------------
if __name__ == "__main__":
    main()