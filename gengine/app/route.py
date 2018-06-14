
def config_routes(config):
    config.add_route('get_progress', '/progress/{user_id}')
    config.add_route('get_position_user', '/position_user/{user_id}')
    config.add_route('get_leaderboard_achievement', '/leaderboard/{achievement_id}')
    config.add_route('get_leaderboard_user', '/leaderboard/{user_id}/{achievement_id}/{relevance}')
    config.add_route('increase_value', '/increase_value/{variable_name}/{user_id}')
    config.add_route('increase_value_with_key', '/increase_value/{variable_name}/{user_id}/{key}')
    config.add_route('increase_multi_values', '/increase_multi_values')
    config.add_route('add_or_update_user', '/add_or_update_user/{user_id}')
    config.add_route('delete_user', '/delete_user/{user_id}')
    config.add_route('get_achievement_level', '/achievement/{achievement_id}/level/{level}')

    config.add_route('auth_login', '/auth/login')

    config.add_route('register_device', '/register_device/{user_id}')
    config.add_route('get_messages', '/messages/{user_id}')
    config.add_route('read_messages', '/read_messages/{user_id}')

    config.add_route('add_Achivement', '/add_Achivement')
    config.add_route('add_Variable', '/add_Variable')
    config.add_route('add_Achivement_Properties', '/add_Achivement_Properties')
    config.add_route('add_Reward', '/add_Achivement_Rewards')

    config.add_route('index', '/index')
    config.add_route('upload','/upload')
    config.add_route('goal','/goal')
    config.add_route('dashbord','/dashbord')
    