# -*- coding: utf-8 -*-
import traceback

import binascii
from http.cookies import SimpleCookie
from flask import Flask, render_template
from pyramid.httpexceptions import HTTPFound
import pyexcel as p
#import pyramid_excel as excel
#import pyexcel.ext.csv  # noqa
import os
import numpy as np

import base64
import copy
import datetime
import json
import pytz
from pyramid.request import Request
from pyramid.response import Response
from pyramid.settings import asbool
from sqlalchemy.sql.expression import select, and_

from gengine.app.permissions import perm_own_update_user_infos, perm_global_update_user_infos, perm_global_delete_user, perm_own_delete_user, \
    perm_global_access_admin_ui, perm_global_register_device, perm_own_register_device, perm_global_read_messages, \
    perm_own_read_messages
from gengine.base.model import valid_timezone, exists_by_expr, update_connection
from gengine.base.errors import APIError
from pyramid.exceptions import NotFound
from pyramid.renderers import render, render_to_response
from pyramid.view import view_config
from pyramid.wsgi import wsgiapp2
from werkzeug import DebuggedApplication

from gengine.app.admin import adminapp
from gengine.app.formular import FormularEvaluationException
from gengine.app.model import (
    User,
    Achievement,
    Value,
    Variable,
    AuthUser, AuthToken, t_users, AchievementProperty, Reward, AchievementCategory, Goal, AchievementReward,
    t_auth_users, t_auth_users_roles, t_auth_roles, t_auth_roles_permissions, UserDevice,
    t_user_device, t_user_messages, UserMessage)
from gengine.base.settings import get_settings
from gengine.metadata import DBSession
from gengine.wsgiutil import HTTPSProxied

@view_config(route_name="upload",renderer="gengine.app:templates/index/upload.jinja2")
def upload_view(request):
    params = request.GET
    dir_name = os.path.dirname(os.path.abspath(__file__))+"\\csv_uploads\\file.csv"
    if request.method == 'POST':
        if 'upload' in request.POST:
            content = request.POST['file'].file
            content = content.read()
            content = content.decode('utf-8', 'ignore')

            my_dict = p.get_book(file_type="csv", file_content=content, delimiter=';')
            my_dict.save_as(dir_name, delimiter=';')

            with open(dir_name) as f:
                keys = f.readline().rstrip().split(";")

            return render_to_response('gengine.app:templates/index/upload.jinja2',
                              {'keys':keys,'params':params}, request=request)
        else:
            user_id = request.POST["user_id"]
            user_region = request.POST["region"]
            user_city = request.POST["city"]
            user_att = []
            for key, item in request.POST.items():
                if key == 'users':
                    user_att.append(item)
            #for i in range(0,len(user_att)):
                #print('user',user_att[i])
            User.add_multiple(user_id,user_region,user_city,user_att,dir_name)
            params.update({'user_id':user_id})
            return HTTPFound(request.route_url('goal',_query=params))
    else:
        return {'params':params}

@view_config(route_name="goal",renderer="gengine.app:templates/index/goal.jinja2")
def goal(request):
    params = request.GET
    dir_name = os.path.dirname(os.path.abspath(__file__))+"\\csv_uploads\\file.csv"
    if request.method == 'POST':
        user_id = params["user_id"]
        variable = request.POST["variable"]
        goal_name = request.POST["goal_name"]
        goal_goal = request.POST["goal_goal"]
        achievement_id = params["id"]
        goal_condition = request.POST["goal_condition"]
        Variable.add_variable(variable)
        Goal.add_goal(goal_name,goal_condition,goal_goal,achievement_id)
        Value.increase(achievement_id,variable,user_id,dir_name)
        return HTTPFound(request.route_url('leaderboard',_query=params))
    else:
        with open(dir_name) as f:
            keys = f.readline().rstrip().split(";")
        return {'keys':keys,'params':params}

@view_config(route_name="leaderboard", renderer="gengine.app:templates/index/leaderboard.jinja2")
def leaderboard(request):
    params = request.GET
    achievement_id = params["id"]
    sorted_by = {"type":"Global"}
    achievement = Achievement.get_achievement(achievement_id)
    if request.method == 'POST':
        if ('sorted_value' in request.POST):
            sorted_by["type"]=params["type"]
            sorted_by.update({'value':request.POST['sorted_value']})
            result = Achievement.get_leaderbord_by_relevance(achievement_id,sorted_by)
            header_table = []
            for key, value in result[0]["user"]["additional_public_data"].items():
                header_table.append(key)
            return {'header_table':header_table,'result':result,'winner':result[0],'params':params,'sorted_by':sorted_by["type"],'achievement':achievement,'sorted_value':request.POST['sorted_value']}
        elif ('sorted_by' in request.POST):
            sorted_by["type"] = request.POST['sorted_by']
            params.update({'type':request.POST['sorted_by']})
            if sorted_by["type"]=='Global':
                result = Achievement.get_leaderbord_by_achievement(achievement_id)
                header_table = []
                for key, value in result[0]["user"]["additional_public_data"].items():
                    header_table.append(key)
                return {'header_table':header_table,'result':result,'winner':result[0],'params':params,'sorted_by':sorted_by["type"],'achievement':achievement}
            else:
                sort_res = User.sort(sorted_by["type"])
                myarray = []
                myarray = np.asarray(sort_res)
                result = Achievement.get_leaderbord_by_achievement(achievement_id)
                header_table = []
                for key, value in result[0]["user"]["additional_public_data"].items():
                    header_table.append(key)
                return {'header_table':header_table,'result':result,'winner':result[0],'exist':sort_res,'sort_res':myarray,'params':params,'sorted_by':sorted_by["type"],'achievement':achievement}
    else:
        result = Achievement.get_leaderbord_by_achievement(achievement_id)
        header_table = []
        for key, value in result[0]["user"]["additional_public_data"].items():
            header_table.append(key)
        return {'header_table':header_table,'result':result,'winner':result[0],'params':params,'sorted_by':sorted_by["type"],'achievement':achievement}

@view_config(route_name="increase_data",renderer="gengine.app:templates/index/increase_data.jinja2")
def increase_data(request):
    dir_name = os.path.dirname(os.path.abspath(__file__))+"\\csv_uploads\\file.csv"
    params = request.GET
    if request.method == 'POST':
        if 'upload' in request.POST:
            dir_name = os.path.dirname(os.path.abspath(__file__))+"\\csv_uploads\\values_data.csv"
            content = request.POST['file'].file
            content = content.read()
            content = content.decode('utf-8', 'ignore')

            my_dict = p.get_book(file_type="csv", file_content=content, delimiter=';')
            my_dict.save_as(dir_name, delimiter=';')

            with open(dir_name) as f:
                keys_data = f.readline().rstrip().split(";")
            params.update({'id':request.POST['achievement_id']})
            return render_to_response('gengine.app:templates/index/increase_data.jinja2',
                              {'keys_data':keys_data,'params':params}, request=request)
        elif 'value' in request.POST:
            user_id = request.POST["user_id"]
            variable = request.POST["variable"]
            value = request.POST["value"]
            user_id_value = request.POST["user_id_value"]
            achievement_id = request.POST['achievement_id']
            res_id_user = User.get_by_id(user_id,user_id_value)
            Value.increaseByValue(variable,res_id_user,value)
            Achievement.update_user_value(achievement_id,res_id_user)
            return HTTPFound(request.route_url('increase_data',_query=params))
        else:
            user_id = request.POST["user_id"]
            variable = request.POST["variable"]
            achievement_id = params["id"]
            Value.increase(achievement_id,variable,user_id,dir_name)
            return HTTPFound(request.route_url('leaderboard',_query=params))
    else:
        with open(dir_name) as f:
            keys = f.readline().rstrip().split(";")
        achievements = Achievement.get_all_achievements()
        return {'achievements':achievements,'params':params,'keys':keys}

@view_config(route_name="tables",renderer="gengine.app:templates/index/tables.jinja2")
def tables(request):
    params = request.GET
    if request.method == 'POST':
        params.update({'id':request.POST['achievement_id']})
        return HTTPFound(request.route_url('leaderboard',_query=params))
    else:
        achievements = Achievement.get_all_achievements()
        return {'achievements':achievements,'params':params}

@view_config(route_name="progress_user",renderer="gengine.app:templates/index/progress_user.jinja2")
def progress_user(request):
    dir_name = os.path.dirname(os.path.abspath(__file__))+"\\csv_uploads\\file.csv"
    params = request.GET
    with open(dir_name) as f:
        keys = f.readline().rstrip().split(";")
    achievements = Achievement.get_all_achievements()
    if request.method == 'POST':
        achievement_id = request.POST['achievement_id']
        user_id = request.POST['user_id']
        sort_by = request.POST['sort_by']
        user_id_value = request.POST['user_id_value']
        res_id_user = User.get_by_id(user_id,user_id_value)
        leaderboard = Achievement.get_leaderbord_by_user(achievement_id,res_id_user,sort_by)
        user = leaderboard['leaderboard'][leaderboard['user_position']]
        user_object = User.get_user(res_id_user)
        prog = Achievement.evaluate(user_object, achievement_id, achievement_date=None, execute_triggers=True)
        rewards = []
        badges = []
        current_level = prog['level']
        all_rewards = AchievementReward.get_rewards(achievement_id,6)
        all_badges = AchievementReward.get_rewards(achievement_id,1)
        for i in range(0,len(all_rewards)):
            if all_rewards[i]['from_level'] <= current_level:
               rewards.append(all_rewards[i]['value'])
        for i in range(0,len(all_badges)):
            if all_badges[i]['from_level'] <= current_level:
               badges.append(all_badges[i]['value'])
        """
        levels = prog['levels']
        for key,value in levels.items():
            if value['level'] <= current_level:
                for key,value in value['rewards'].items():
                    if value['name'] == 'badge':
                        badges.append(value['value'])
                    if value['name'] == 'reward':
                        rewards.append(value['value'])
        """
        header_user = []
        for key, value in user['user']['additional_public_data'].items():
            header_user.append(key)
        return {'header_user':header_user,'user':user,'achievements':achievements,'params':params,'keys':keys,'badges':badges,'rewards':rewards,'current_level':current_level}
    else:
        return {'achievements':achievements,'params':params,'keys':keys}


@view_config(route_name="badges",renderer="gengine.app:templates/index/badges.jinja2")
def badges(request):
    params = request.GET
    achievements = Achievement.get_all_achievements()
    if request.method == 'POST':
        if 'achievement_id' in request.POST:
            achievement_id = request.POST['achievement_id']
            achievement = Achievement.get_achievement(achievement_id)
            rewards = AchievementReward.get_rewards(achievement_id,6)
            badges = AchievementReward.get_rewards(achievement_id,1)
            nb_levels = (int)(achievement["maxlevel"]/5)
            if not badges:
                AchievementReward.create_achievement_rewards_badges(achievement_id,"badge1.PNG",1)
                AchievementReward.create_achievement_rewards_badges(achievement_id,"badge2.PNG",nb_levels)
                AchievementReward.create_achievement_rewards_badges(achievement_id,"badge3.PNG",nb_levels*2)
                AchievementReward.create_achievement_rewards_badges(achievement_id,"badge4.PNG",nb_levels*3)
                AchievementReward.create_achievement_rewards_badges(achievement_id,"badge5.PNG",nb_levels*4)
                AchievementReward.create_achievement_rewards_badges(achievement_id,"badge6.PNG",nb_levels*5)
            achievement_id = request.POST['achievement_id']
            return {'selected_achievement':achievement_id,'achievements':achievements,'params':params,'levels':nb_levels,'rewards':rewards}
        else:
            reward_name = request.POST['reward_name']
            reward_level = request.POST['reward_level']
            selected_achievement = request.POST['selected_achievement']
            AchievementReward.create_achievement_rewards(selected_achievement, reward_name, reward_level)
            return {'achievements':achievements,'params':params}
    else:
        return {'achievements':achievements,'params':params}

@view_config(route_name="index",renderer="gengine.app:templates/index/index.jinja2")
def index(request):
    return {}

@view_config(route_name="dashbord",renderer="gengine.app:templates/index/dashbord.jinja2")
def dashbord(request):
    return {}

@view_config(route_name="login",renderer="gengine.app:templates/index/login.jinja2")
def login(request):
    return {}


@view_config(route_name='progress_users', renderer='json', request_method="GET")
def progress_users(request):
    achievement_id = int(request.matchdict["achievement_id"])
    leaderboard = Achievement.get_leaderbord_by_achievement(achievement_id)
    progress = Achievement.get_achievement_max_value(achievement_id)
    return {"max_value":progress,"leaderboard" : leaderboard}

@view_config(route_name='users_cities', renderer='json', request_method="GET")
def users_cities(request):
    achievement_id = int(request.matchdict["achievement_id"])
    cities = User.sort("City")
    res_cities = []
    res_cities = np.asarray(cities)
    result = []
    for i in range(len(res_cities)):
        relevance = {'type':'City','value':res_cities[i][0]}
        result.append({'City':res_cities[i][0],'Leaderboard':Achievement.get_leaderbord_by_relevance(achievement_id,relevance)}) 
    return result

@view_config(route_name="achievements_all", renderer='json', request_method="GET")
def achievements_all(request):
    achievements = Achievement.get_all_achievements()
    result = []
    for achievement in achievements:
        result.append({"id":achievement["id"],"name":achievement["name"]})
    return {'achievements':result}


@view_config(route_name='add_or_update_user', renderer='string', request_method="POST")
def add_or_update_user(request):
    """add a user and set its metadata"""

    user_id = int(request.matchdict["user_id"])

    if asbool(get_settings().get("enable_user_authentication", False)):
        #ensure that the user exists and we have the permission to update it
        may_update = request.has_perm(perm_global_update_user_infos) or request.has_perm(perm_own_update_user_infos) and request.user.id == user_id
        if not may_update:
            raise APIError(403, "forbidden", "You may not edit this user.")

        #if not exists_by_expr(t_users,t_users.c.id==user_id):
        #    raise APIError(403, "forbidden", "The user does not exist. As the user authentication is enabled, you need to create the AuthUser first.")


    lat=None
    if len(request.POST.get("lat",""))>0:
        lat = float(request.POST["lat"])
    
    lon=None
    if len(request.POST.get("lon",""))>0:
        lon = float(request.POST["lon"])
    
    friends=[]
    if len(request.POST.get("friends",""))>0:
        friends = [int(x) for x in request.POST["friends"].split(",")]
    
    groups=[]
    if len(request.POST.get("groups",""))>0:
        groups = [int(x) for x in request.POST["groups"].split(",")]
    
    timezone="UTC"
    if len(request.POST.get("timezone",""))>0:
        timezone = request.POST["timezone"]
    
    if not valid_timezone(timezone):
        timezone = 'UTC'
    
    country=None
    if len(request.POST.get("country",""))>0:
        country = request.POST["country"]
    
    region=None
    if len(request.POST.get("region",""))>0:
        region = request.POST["region"]
    
    city=None
    if len(request.POST.get("city",""))>0:
        city = request.POST["city"]

    language = None
    if len(request.POST.get("language", "")) > 0:
        language= request.POST["language"]

    additional_public_data = {}
    if len(request.POST.get("additional_public_data", "")) > 0:
        try:
            additional_public_data = json.loads(request.POST["additional_public_data"])
        except:
            additional_public_data = {}


    User.set_infos(user_id=user_id,
                   lat=lat,
                   lng=lon,
                   timezone=timezone,
                   country=country,
                   region=region,
                   city=city,
                   language=language,
                   friends=friends,
                   groups=groups,
                   additional_public_data = additional_public_data)
    return {"status": "OK", "user" : User.full_output(user_id)}

@view_config(route_name='delete_user', renderer='string', request_method="DELETE")
def delete_user(request):
    """delete a user completely"""
    user_id = int(request.matchdict["user_id"])

    """if asbool(get_settings().get("enable_user_authentication", False)):
        # ensure that the user exists and we have the permission to update it
        may_delete = request.has_perm(perm_global_delete_user) or request.has_perm(perm_own_delete_user) and request.user.id == user_id
        if not may_delete:
            raise APIError(403, "forbidden", "You may not delete this user.")"""

    User.delete_user(user_id)

    return {"status": "OK"}

def _get_progress(achievements_for_user, requesting_user):

    achievements = Achievement.get_achievements_by_user_for_today(achievements_for_user)

    def ea(achievement, achievement_date, execute_triggers):
        try:
            return Achievement.evaluate(achievements_for_user, achievement["id"], achievement_date, execute_triggers=execute_triggers)
        except FormularEvaluationException as e:
            return { "error": "Cannot evaluate formular: " + e.message, "id" : achievement["id"] }
        except Exception as e:
            tb = traceback.format_exc()
            return { "error": tb, "id" : achievement["id"] }

    check = lambda x : x!=None and not "error" in x and (x["hidden"]==False or x["level"]>0)

    def may_view(achievement, requesting_user):
        if not asbool(get_settings().get("enable_user_authentication", False)):
            return True
        if achievement["view_permission"] == "everyone":
            return True
        if achievement["view_permission"] == "own" and achievements_for_user["id"] == requesting_user["id"]:
            return True
        return False

    evaluatelist = []
    now = datetime.datetime.now(pytz.timezone(achievements_for_user["timezone"]))
    for achievement in achievements:
        if may_view(achievement, requesting_user):
            achievement_dates = set()
            d = max(achievement["created_at"], achievements_for_user["created_at"]).replace(tzinfo=pytz.utc)
            dr = Achievement.get_datetime_for_evaluation_type(
                achievement["evaluation_timezone"],
                achievement["evaluation"],
                dt=d
            )

            achievement_dates.add(dr)
            if dr != None:
                while d <= now:
                    if achievement["evaluation"] == "yearly":
                        d += datetime.timedelta(days=364)
                    elif achievement["evaluation"] == "monthly":
                        d += datetime.timedelta(days=28)
                    elif achievement["evaluation"] == "weekly":
                        d += datetime.timedelta(days=6)
                    elif achievement["evaluation"] == "daily":
                        d += datetime.timedelta(hours=23)
                    else:
                        break # should not happen

                    dr = Achievement.get_datetime_for_evaluation_type(
                        achievement["evaluation_timezone"],
                        achievement["evaluation"],
                        dt=d
                    )

                    if dr <= now:
                        achievement_dates.add(dr)

            i=0
            for achievement_date in reversed(sorted(achievement_dates)):
                # We execute the goal triggers only for the newest and previous period, not for any periods longer ago
                # (To not send messages for very old things....)
                evaluatelist.append(ea(achievement, achievement_date, execute_triggers=(i == 0 or i == 1 or achievement_date == None)))
                i += 1


    ret = {
        "achievements" : [
            x for x in evaluatelist if check(x)
        ],
        "achievement_errors" : [
            x for x in evaluatelist if x!=None and "error" in x
        ]
    }

    return ret

@view_config(route_name='get_leaderboard_achievement', renderer='json', request_method="GET")
def get_leaderboard_achievement(request):

    try:
        achievement_id = int(request.matchdict["achievement_id"])
    except:
        raise APIError(400, "illegal_achievement_id", "no valid achievement_id given")

    return Achievement.get_leaderbord_by_achievement(achievement_id)

@view_config(route_name='get_leaderboard_user', renderer='json', request_method="GET")
def get_leaderboard_user(request):

    try:
        achievement_id = int(request.matchdict["achievement_id"])
    except:
        raise APIError(400, "illegal_achievement_id", "no valid achievement_id given")

    try:
        user_id = int(request.matchdict["user_id"])
    except:
        raise APIError(400, "illegal_user_id", "no valid user_id given")

    relevance='global'
    if len(request.matchdict["relevance"])>0:
        relevance = request.matchdict["relevance"]
    #relevance = request.matchdict["relevance"]
    #print('relevance',relevance)

    return Achievement.get_leaderbord_by_user(achievement_id,user_id,relevance)

@view_config(route_name='get_progress', renderer='json', request_method="GET")
def get_progress(request):
    """get all relevant data concerning the user's progress"""
    try:
        user_id = int(request.matchdict["user_id"])
    except:
        raise APIError(400, "illegal_user_id", "no valid user_id given")
    
    user = User.get_user(user_id)
    if not user:
        raise APIError(404, "user_not_found", "user not found")

    output = _get_progress(achievements_for_user=user, requesting_user=request.user)
    output = copy.deepcopy(output)

    for i in range(len(output["achievements"])):
        if "new_levels" in output["achievements"][i]:
            del output["achievements"][i]["new_levels"]

    return output


@view_config(route_name='add_Achivement', renderer='json', request_method="POST")
def add_Achivement(request):
    
    achievementCategory = AchievementCategory()
    achievementCategory.name = request.POST["category"]
    DBSession.add(achievementCategory)
    DBSession.flush()

    achievement = Achievement()
    achievement.name = request.POST["achievement_name"]
    achievement.valid_start = request.POST["achievement_valid_start"]
    achievement.valid_end = request.POST["achievement_valid_end"]
    achievement.maxlevel = request.POST["achievement_maxlevel"]
    achievement.relevance = "global"
    achievement.evaluation_timezone = "UTC"
    achievement.achievementcategory_id = achievementCategory.id
    
    """
    achievement.lat = 0
    achievement.lng = 0
    achievement.max_distance = 0
    achievement.evaluation = "immediately"
    #to add with edit after creating groups and friends users
    achievement.relevance = "friends"
    achievement.view_permission = request.POST["achievement_view_permission"]
    """
    
    DBSession.add(achievement)
    DBSession.flush()
    params = {"id": achievement.id}
    #params = {"id": "7"}
    return HTTPFound(request.route_url('upload',_query=params))

@view_config(route_name='add_Variable', renderer='json', request_method="POST")
def add_Variable(request):

    variable = Variable()
    variable.name = request.POST["variable_name"]
    variable.group = request.POST["variable_group"]
    DBSession.add(variable)
    DBSession.flush()

    return {"variable":"ok"}

@view_config(route_name='add_Achivement_Properties', renderer='json', request_method="POST")
def add_Achivement_Properties(request):

    achievementProperty = AchievementProperty()
    achievementProperty.name = request.POST["name"]
    DBSession.add(achievementProperty)
    DBSession.flush()

    return {"Achivement_Properties":"ok"}


@view_config(route_name='add_Reward', renderer='json', request_method="POST")
def add_Reward(request):
    reward = Reward()
    reward.name = request.POST["name"]
    DBSession.add(reward)
    DBSession.flush()

    return {"Achivement_Reward":"ok"}
    
@view_config(route_name='get_position_user', renderer='json', request_method="GET")
def get_position_user(request):
    """get all relevant data concerning the user's progress"""
    try:
        user_id = int(request.matchdict["user_id"])
    except:
        raise APIError(400, "illegal_user_id", "no valid user_id given")
    
    user = User.get_user(user_id)
    if not user:
        raise APIError(404, "user_not_found", "user not found")

    output = _get_progress(achievements_for_user=user, requesting_user=request.user)
    output = copy.deepcopy(output)
    
    Achievements = []
    for i in range(len(output["achievements"])):
        if "new_levels" in output["achievements"][i]:
            del output["achievements"][i]["new_levels"]
        achievement = {}
        achievement["achievement_name"] = output["achievements"][i]["internal_name"]
        achievement["achievement_category"] = output["achievements"][i]["achievementcategory"]
        achievement["maxlevel"] = output["achievements"][i]["maxlevel"]
        achievement["level"] = output["achievements"][i]["level"]
        goals = output["achievements"][i]["goals"]
        for goal in goals:
            if "leaderboard" in goals[goal]:
                del goals[goal]["leaderboard"]
            if "properties" in goals[goal]:
                del goals[goal]["properties"]
            if "priority" in goals[goal]:
                del goals[goal]["priority"]
            if "leaderboard_position" in goals[goal]:
                goals[goal]["leaderboard_position"] = goals[goal]["leaderboard_position"] + 1
        achievement["goals"] = goals
        Achievements.append(achievement)
    res = {'user':user["id"],'achievements':Achievements}
    
    return res

@view_config(route_name='increase_value', renderer='json', request_method="POST")
@view_config(route_name='increase_value_with_key', renderer='json', request_method="POST")
def increase_value(request):
    """increase a value for the user"""
    
    user_id = int(request.matchdict["user_id"])
    try:
        value = float(request.POST["value"])
    except:
        try:
            doc = request.json_body
            value = doc["value"]
        except:
            raise APIError(400,"invalid_value","Invalid value provided")
    
    key = request.matchdict["key"] if ("key" in request.matchdict and request.matchdict["key"] is not None) else ""
    variable_name = request.matchdict["variable_name"]
    
    user = User.get_user(user_id)
    if not user:
        raise APIError(404, "user_not_found", "user not found")
    
    variable = Variable.get_variable_by_name(variable_name)
    if not variable:
        raise APIError(404, "variable_not_found", "variable not found")

    if asbool(get_settings().get("enable_user_authentication", False)):
        if not Variable.may_increase(variable, request, user_id):
            raise APIError(403, "forbidden", "You may not increase the variable for this user.")
    
    Value.increase_value(variable_name, user, value, key) 
    
    output = _get_progress(achievements_for_user=user, requesting_user=request.user)
    output = copy.deepcopy(output)
    to_delete = list()
    for i in range(len(output["achievements"])):
        if len(output["achievements"][i]["new_levels"])>0:
            if "levels" in output["achievements"][i]:
                del output["achievements"][i]["levels"]
            if "priority" in output["achievements"][i]:
                del output["achievements"][i]["priority"]
            if "goals" in output["achievements"][i]:
                del output["achievements"][i]["goals"]
        else:
            to_delete.append(i)

    for i in sorted(to_delete,reverse=True):
        del output["achievements"][i]

    return output

@view_config(route_name="increase_multi_values", renderer="json", request_method="POST")
def increase_multi_values(request):
    try:
        doc = request.json_body
    except:
        raise APIError(400, "invalid_json", "no valid json body")
    ret = {}
    for user_id, values in doc.items():
        user = User.get_user(user_id)
        if not user:
            raise APIError(404, "user_not_found", "user %s not found" % (user_id,))

        for variable_name, values_and_keys in values.items():
            for value_and_key in values_and_keys:
                variable = Variable.get_variable_by_name(variable_name)

                if asbool(get_settings().get("enable_user_authentication", False)):
                    if not Variable.may_increase(variable, request, user_id):
                        raise APIError(403, "forbidden", "You may not increase the variable %s for user %s." % (variable_name, user_id))
                
                if not variable:
                    raise APIError(404, "variable_not_found", "variable %s not found" % (variable_name,))

                if not 'value' in value_and_key:
                    raise APIError(400, "variable_not_found", "illegal value for %s" % (variable_name,))
                
                value = value_and_key['value']
                key = value_and_key.get('key','')
                
                Value.increase_value(variable_name, user, value, key)

        output = _get_progress(achievements_for_user=user, requesting_user=request.user)
        output = copy.deepcopy(output)
        to_delete = list()
        for i in range(len(output["achievements"])):
            if len(output["achievements"][i]["new_levels"])>0:
                if "levels" in output["achievements"][i]:
                    del output["achievements"][i]["levels"]
                if "priority" in output["achievements"][i]:
                    del output["achievements"][i]["priority"]
                if "goals" in output["achievements"][i]:
                    del output["achievements"][i]["goals"]
            else:
                to_delete.append(i)

        for i in sorted(to_delete, reverse=True):
            del output["achievements"][i]

        if len(output["achievements"])>0 :
            ret[user_id]=output
    
    return ret

@view_config(route_name='get_achievement_level', renderer='json', request_method="GET")
def get_achievement_level(request):
    """get all information about an achievement for a specific level""" 
    try:
        achievement_id = int(request.matchdict.get("achievement_id",None))
        level = int(request.matchdict.get("level",None))
    except:
        raise APIError(400, "invalid_input", "invalid input")

    achievement = Achievement.get_achievement(achievement_id)

    if not achievement:
        raise APIError(404, "achievement_not_found", "achievement not found")

    level_output = Achievement.basic_output(achievement, [], True, level).get("levels").get(str(level), {"properties": {}, "rewards": {}})
    if "goals" in level_output:
        del level_output["goals"]
    if "level" in level_output:
        del level_output["level"]

    return level_output


@view_config(route_name='auth_login', renderer='json', request_method="POST")
def auth_login(request):
    try:
        doc = request.json_body
    except:
        raise APIError(400, "invalid_json", "no valid json body")

    user = request.user
    email = doc.get("email")
    password = doc.get("password")

    if user:
        #already logged in
        token = user.get_or_create_token().token
    else:
        if not email or not password:
            raise APIError(400, "login.email_and_password_required", "You need to send your email and password.")

        user = DBSession.query(AuthUser).filter_by(email=email).first()

        if not user or not user.verify_password(password):
            raise APIError(401, "login.email_or_password_invalid", "Either the email address or the password is wrong.")

        if not user.active:
            raise APIError(400, "user_is_not_activated", "Your user is not activated.")

        token = AuthToken.generate_token()
        tokenObj = AuthToken(
            user_id = user.id,
            token = token
        )

        DBSession.add(tokenObj)

    return {
        "token" : token,
        "user" : User.full_output(user.user_id),
    }

@view_config(route_name='register_device', renderer='json', request_method="POST")
def register_device(request):
    try:
        doc = request.json_body
    except:
        raise APIError(400, "invalid_json", "no valid json body")

    user_id = int(request.matchdict["user_id"])

    device_id = doc.get("device_id")
    push_id = doc.get("push_id")
    device_os = doc.get("device_os")
    app_version = doc.get("app_version")

    if not device_id \
            or not push_id \
            or not user_id \
            or not device_os \
            or not app_version:
        raise APIError(400, "register_device.required_fields",
                       "Required fields: device_id, push_id, device_os, app_version")

    if asbool(get_settings().get("enable_user_authentication", False)):
        may_register = request.has_perm(perm_global_register_device) or request.has_perm(
            perm_own_register_device) and str(request.user.id) == str(user_id)
        if not may_register:
            raise APIError(403, "forbidden", "You may not register devices for this user.")

    if not exists_by_expr(t_users, t_users.c.id==user_id):
        raise APIError(404, "register_device.user_not_found",
                       "There is no user with this id.")

    UserDevice.add_or_update_device(user_id = user_id, device_id = device_id, push_id = push_id, device_os = device_os, app_version = app_version)

    return {
        "status" : "ok"
    }

@view_config(route_name='get_messages', renderer='json', request_method="GET")
def get_messages(request):
    try:
        user_id = int(request.matchdict["user_id"])
    except:
        user_id = None

    try:
        offset = int(request.GET.get("offset",0))
    except:
        offset = 0

    limit = 100

    if asbool(get_settings().get("enable_user_authentication", False)):
        may_read_messages = request.has_perm(perm_global_read_messages) or request.has_perm(
            perm_own_read_messages) and str(request.user.id) == str(user_id)
        if not may_read_messages:
            raise APIError(403, "forbidden", "You may not read the messages of this user.")

    if not exists_by_expr(t_users, t_users.c.id == user_id):
        raise APIError(404, "get_messages.user_not_found",
                       "There is no user with this id.")

    q = t_user_messages.select().where(t_user_messages.c.user_id==user_id).order_by(t_user_messages.c.created_at.desc()).limit(limit).offset(offset)
    rows = DBSession.execute(q).fetchall()

    return {
        "messages" : [{
            "id" : message["id"],
            "text" : UserMessage.get_text(message),
            "is_read" : message["is_read"],
            "created_at" : message["created_at"]
        } for message in rows]
    }


@view_config(route_name='read_messages', renderer='json', request_method="POST")
def set_messages_read(request):
    try:
        doc = request.json_body
    except:
        raise APIError(400, "invalid_json", "no valid json body")

    user_id = int(request.matchdict["user_id"])

    if asbool(get_settings().get("enable_user_authentication", False)):
        may_read_messages = request.has_perm(perm_global_read_messages) or request.has_perm(
            perm_own_read_messages) and str(request.user.id) == str(user_id)
        if not may_read_messages:
            raise APIError(403, "forbidden", "You may not read the messages of this user.")

    if not exists_by_expr(t_users, t_users.c.id == user_id):
        raise APIError(404, "set_messages_read.user_not_found", "There is no user with this id.")

    message_id = doc.get("message_id")
    q = select([t_user_messages.c.id,
        t_user_messages.c.created_at], from_obj=t_user_messages).where(and_(t_user_messages.c.id==message_id,
                                                                       t_user_messages.c.user_id==user_id))
    msg = DBSession.execute(q).fetchone()
    if not msg:
        raise APIError(404, "set_messages_read.message_not_found", "There is no message with this id.")

    uS = update_connection()
    uS.execute(t_user_messages.update().values({
        "is_read" : True
    }).where(and_(
        t_user_messages.c.user_id == user_id,
        t_user_messages.c.created_at <= msg["created_at"]
    )))

    return {
        "status" : "ok"
    }

@view_config(route_name='admin_app')
@wsgiapp2
def admin_tenant(environ, start_response):

    def admin_app(environ, start_response):
        #return HTTPSProxied(DebuggedApplication(adminapp.wsgi_app, True))(environ, start_response)
        return HTTPSProxied(adminapp.wsgi_app)(environ, start_response)

    def request_auth(environ, start_response):
        resp = Response()
        resp.status_code = 401
        resp.www_authenticate = 'Basic realm="%s"' % ("Gamification Engine Admin",)
        return resp(environ, start_response)

    if not asbool(get_settings().get("enable_user_authentication", False)):
        return admin_app(environ, start_response)

    req = Request(environ)

    def _get_basicauth_credentials(request):
        authorization = request.headers.get("authorization","")
        try:
            authmeth, auth = authorization.split(' ', 1)
        except ValueError:  # not enough values to unpack
            return None
        if authmeth.lower() == 'basic':
            try:
                auth = base64.b64decode(auth.strip()).decode("UTF-8")
            except binascii.Error:  # can't decode
                return None
            try:
                login, password = auth.split(':', 1)
            except ValueError:  # not enough values to unpack
                return None
            return {'login': login, 'password': password}
        return None

    user = None
    cred = _get_basicauth_credentials(req)
    token = req.cookies.get("token",None)
    if token:
        tokenObj = DBSession.query(AuthToken).filter(AuthToken.token == token).first()
        user = None
        if tokenObj and tokenObj.valid_until < datetime.datetime.utcnow():
            tokenObj.extend()
        if tokenObj:
            user = tokenObj.user

    if not user:
        if cred:
            user = DBSession.query(AuthUser).filter_by(email=cred["login"]).first()
        if not user or not user.verify_password(cred["password"]):
            return request_auth(environ, start_response)

    if user:
        j = t_auth_users.join(t_auth_users_roles).join(t_auth_roles).join(t_auth_roles_permissions)
        q = select([t_auth_roles_permissions.c.name], from_obj=j).where(t_auth_users.c.user_id==user.user_id)
        permissions = [r["name"] for r in DBSession.execute(q).fetchall()]
        if not perm_global_access_admin_ui in permissions:
            return request_auth(environ, start_response)
        else:
            token_s = user.get_or_create_token().token

            def start_response_with_headers(status, headers, exc_info=None):

                cookie = SimpleCookie()
                cookie['X-Auth-Token'] = token_s
                cookie['X-Auth-Token']['path'] = get_settings().get("urlprefix", "").rstrip("/") + "/"

                headers.append(('Set-Cookie', cookie['X-Auth-Token'].OutputString()),)

                return start_response(status, headers, exc_info)

            return admin_app(environ, start_response_with_headers)