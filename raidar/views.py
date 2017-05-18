from json import dumps as json_dumps, loads as json_loads
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.middleware.csrf import get_token
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from evtcparser.parser import Encounter as EvtcEncounter, EvtcParseException
from analyser.analyser import Analyser, Group, Archetype, EvtcAnalysisException
from django.utils import timezone
from time import time
from django.db import transaction
from django.core import serializers
from re import match
from .models import *
from itertools import groupby
from zipfile import ZipFile
from gw2api.gw2api import GW2API, GW2APIException
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm




def _safe_get(f):
    try:
        return f()
    except KeyError:
        return None

def _error(msg, **kwargs):
    kwargs['error'] = str(msg)
    return JsonResponse(kwargs)


def _userprops(request):
    if request.user:
        return {
                'username': request.user.username,
                'is_staff': request.user.is_staff
            }
    else:
        return {}

def _participation_data(participation):
    return {
            'id': participation.encounter.id,
            'area': participation.encounter.area.name,
            'started_at': participation.encounter.started_at,
            'duration': participation.encounter.duration,
            'character': participation.character.name,
            'account': participation.character.account.name,
            'profession': participation.character.profession,
            'archetype': participation.archetype,
            'elite': participation.elite,
            'uploaded_at': participation.encounter.uploaded_at,
        }


def _encounter_data(request):
    participations = Participation.objects.filter(character__account__user=request.user).select_related('encounter', 'character', 'character__account')
    return [_participation_data(participation) for participation in participations]

def _login_successful(request, user):
    auth_login(request, user)
    csrftoken = get_token(request)
    userprops = _userprops(request)
    userprops['csrftoken'] = csrftoken
    userprops['encounters'] = _encounter_data(request)
    return JsonResponse(userprops)




def _html_response(request, page, data={}):
    response = _userprops(request)
    response.update(data)
    response['archetypes'] = {k: v for k, v in Participation.ARCHETYPE_CHOICES}
    response['specialisations'] = {p: {e: n for (pp, e), n in Character.SPECIALISATIONS.items() if pp == p} for p, _ in Character.PROFESSION_CHOICES}
    response['page'] = page
    return render(request, template_name='raidar/index.html', context={
            'userprops': json_dumps(response),
        })

@require_GET
def index(request, page={ 'name': 'encounters', 'no': 1 }):
    return _html_response(request, page)

@require_GET
def encounter(request, id=None, json=None):
    encounter = Encounter.objects.select_related('area').get(pk=id)
    own_account_names = [account.name for account in Account.objects.filter(
        characters__participations__encounter_id=encounter.id,
        user=request.user)]
    dump = json_loads(encounter.dump)
    area_stats = json_loads(encounter.area.stats)
    phases = dump['Category']['damage']['Phase'].keys()
    members = [{ "name": name, **value } for name, value in dump['Category']['status']['Player'].items()]
    keyfunc = lambda member: member['party']
    parties = { party: {
                    "members": list(members),
                    "stats": {
                        phase: {
                            "actual": dump['Category']['damage']['Phase'][phase]['To']['*All']['Subgroup'][str(party)],
                            "actual_boss": dump['Category']['damage']['Phase'][phase]['To']['*Boss']['Subgroup'][str(party)],
                        } for phase in phases
                    }
                } for party, members in groupby(sorted(members, key=keyfunc), keyfunc) }
    for party_no, party in parties.items():
        for member in party['members']:
            if member['account'] in own_account_names:
                member['self'] = True
            member['phases'] = {
                phase: {
                    # too many values... Skills needed?
                    'actual': _safe_get(lambda: dump['Category']['damage']['Phase'][phase]['Player'][member['name']]['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['damage']['Phase'][phase]['Player'][member['name']]['To']['*Boss']),
                    'buffs': _safe_get(lambda: dump['Category']['buffs']['Phase'][phase]['Player'][member['name']]),
                    'archetype': _safe_get(lambda: area_stats[phase]['build'][str(member['profession'])][str(member['elite'])][str(member['archetype'])])
                } for phase in phases
            }
    data = {
        "encounter": {
            "name": encounter.area.name,
            "started_at": encounter.started_at,
            "duration": encounter.duration,
            "phases": {
                phase: {
                    'group': _safe_get(lambda: area_stats[phase]['group']),
                    'individual': _safe_get(lambda: area_stats[phase]['individual']),
                    'actual': _safe_get(lambda: dump['Category']['damage']['Phase'][phase]['To']['*All']),
                    'actual_boss': _safe_get(lambda: dump['Category']['damage']['Phase'][phase]['To']['*Boss']),
                } for phase in phases
            },
            "parties": parties,
        }
    }

    if json:
        return JsonResponse(data)
    else:
        return _html_response(request, { "name": "encounter", "no": str(id) }, data)


@require_GET
def initial(request):
    response = _userprops(request)
    if request.user.is_authenticated():
        response['encounters'] = _encounter_data(request)
    return JsonResponse(response)


def login(request):
    if request.method == 'GET':
        return index(request, page={ 'name': 'login' })

    username = request.POST.get('username')
    password = request.POST.get('password')
    # stayloggedin = request.GET.get('stayloggedin')
    # if stayloggedin == "true":
    #     pass
    # else:
    #     request.session.set_expiry(0)

    user = authenticate(username=username, password=password)
    if user is not None and user.is_active:
        return _login_successful(request, user)
    else:
        return _error('Could not log in')


def register(request):
    if request.method == 'GET':
        return index(request, page={ 'name': 'register' })

    username = request.POST.get('username')
    password = request.POST.get('password')
    email = request.POST.get('email')
    api_key = request.POST.get('api_key')
    gw2api = GW2API(api_key)

    try:
        gw2_account = gw2api.query("/account")
    except GW2APIException as e:
        return _error(e)

    try:
        user = User.objects.create_user(username, email, password)
    except IntegrityError:
        return _error('Such a user already exists')

    if not user:
        return _error('Could not register user')

    account_name = gw2_account['name']
    account, _ = Account.objects.get_or_create(name=account_name)
    account.user = user
    account.api_key = api_key
    account.save()

    return _login_successful(request, user)


@login_required
@require_POST
def logout(request):
    auth_logout(request)
    csrftoken = get_token(request)
    return JsonResponse({})


@login_required
@require_POST
def upload(request):
    result = {}
    # TODO this should really only be one file
    # so make adjustments to find out its name and only provide one result

    for filename, file in request.FILES.items():
        zipfile = None
        if filename.endswith('.evtc.zip'):
            zipfile = ZipFile(file)
            contents = zipfile.infolist()
            if len(contents) == 1:
                file = zipfile.open(contents[0].filename)
            else:
                return _error('Only single-file ZIP archives are allowed')

        try:
            evtc_encounter = EvtcEncounter(file)
        except EvtcParseException as e:
            return _error(e)

        if zipfile:
            zipfile.close()

        area = Area.objects.get(id=evtc_encounter.area_id)
        if not area:
            return _error('Unknown area')

        try:
            analyser = Analyser(evtc_encounter)
        except EvtcAnalysisException as e:
            return _error(e)

        dump = analyser.data

        # XXX

        started_at = dump['Category']['encounter']['start']
        duration = dump['Category']['encounter']['duration']

        if duration < 60:
            return _error('Encounter shorter than 60s')

        # heuristics to see if the encounter is a re-upload:
        # a character can only be in one raid at a time
        # account_names are being hashed, and the triplet
        # (area, account_hash, started_at) is being checked for
        # uniqueness (along with some fuzzing to started_at)
        status_for = dump[Group.CATEGORY]['status']['Player']
        account_names = [player['account'] for player in status_for.values()]
        try:
            encounter, encounter_created = Encounter.objects.get_or_create(
                uploaded_at=time(), uploaded_by=request.user,
                area=area, started_at=started_at, duration=duration,
                account_names=account_names,
                dump=json_dumps(dump)
            )
        except IntegrityError:
            return _error("Already uploaded")

        if encounter_created:
            for name, player in status_for.items():
                account, _ = Account.objects.get_or_create(
                        name=player['account'])
                character, _ = Character.objects.get_or_create(
                        name=name, account=account, profession=player['profession'])
                Participation.objects.create(
                        character=character, encounter=encounter,
                        archetype=player['archetype'], party=player['party'], elite=player['elite'])

        own_participation = encounter.participations.filter(character__account__user=request.user).first()
        if own_participation:
            result[filename] = _participation_data(own_participation)

    return JsonResponse(result)


@require_GET
def named(request, name, no):
    return index(request, { 'name': name, 'no': no })

@login_required
@require_POST
def change_email(request):
    request.user.email = request.POST.get('email')
    request.user.save()
    return JsonResponse({})

@login_required
@require_POST
def change_password(request):
    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return JsonResponse({})
    else:
        return _error(' '.join(' '.join(v) for k, v in form.errors.items()))

@login_required
@require_POST
def add_api_key(request):
    api_key = request.POST.get('api_key')
    gw2api = GW2API(api_key)

    try:
        gw2_account = gw2api.query("/account")
    except GW2APIException as e:
        return _error(e)

    account_name = gw2_account['name']
    account, _ = Account.objects.get_or_create(name=account_name)
    if account.user and account.user != request.user:
        return _error("The associated GW2 account is already registered to another user")

    account.user = request.user
    account.api_key = api_key
    account.save()

    return JsonResponse({
        'account_name': account_name,
        'encounters': _encounter_data(request)
    })
