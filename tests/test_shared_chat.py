import pytest
from app import app as flask_app, db


def create_user(username, email, password='pw123456'):
    from app import User
    u = User(username=username, email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


def login(client, username, password='pw123456'):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=True)


def make_shared(owner):
    from app import SharedAccount, SharedAccountMember
    sa = SharedAccount(name='Chat Test', created_by_user_id=owner.id)
    db.session.add(sa)
    db.session.flush()
    db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
    db.session.commit()
    return sa


def test_message_model_creation():
    from app import SharedAccountMessage, SharedAccountReaction
    with flask_app.app_context():
        u = create_user('m_owner', 'm_owner@test.com')
        sa = make_shared(u)
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=u.id, text='Hello'
        )
        db.session.add(msg)
        db.session.commit()
        assert SharedAccountMessage.query.count() == 1

        reaction = SharedAccountReaction(
            message_id=msg.id, user_id=u.id, emoji='❤️'
        )
        db.session.add(reaction)
        db.session.commit()
        assert SharedAccountReaction.query.count() == 1


def test_send_and_get_message(client):
    from app import SharedAccountMessage
    with flask_app.app_context():
        u = create_user('send_u1', 'send_u1@test.com')
        sa = make_shared(u)
        sa_id = sa.id

    login(client, 'send_u1')
    resp = client.post(f'/api/shared/{sa_id}/messages',
                       data={'text': 'Купи молоко'})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True

    resp = client.get(f'/api/shared/{sa_id}/messages')
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['text'] == 'Купи молоко'
    assert data[0]['is_mine'] is True


def test_non_member_cannot_send(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        owner = create_user('nm_owner', 'nm_owner@test.com')
        create_user('nm_other', 'nm_other@test.com')
        sa = make_shared(owner)
        sa_id = sa.id

    login(client, 'nm_other')
    resp = client.post(f'/api/shared/{sa_id}/messages', data={'text': 'Hello'})
    assert resp.status_code == 403


def test_delete_own_message(client):
    from app import SharedAccountMessage
    with flask_app.app_context():
        u = create_user('del_u1', 'del_u1@test.com')
        sa = make_shared(u)
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=u.id, text='Delete me'
        )
        db.session.add(msg)
        db.session.commit()
        sa_id, msg_id = sa.id, msg.id

    login(client, 'del_u1')
    resp = client.delete(f'/api/shared/{sa_id}/messages/{msg_id}')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True

    with flask_app.app_context():
        assert db.session.get(SharedAccountMessage, msg_id) is None


def test_cannot_delete_others_message(client):
    from app import SharedAccount, SharedAccountMember, SharedAccountMessage
    with flask_app.app_context():
        owner = create_user('prot_owner', 'prot_owner@test.com')
        other = create_user('prot_other', 'prot_other@test.com')
        sa = make_shared(owner)
        db.session.add(SharedAccountMember(
            shared_account_id=sa.id, user_id=other.id
        ))
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=owner.id, text='Protected'
        )
        db.session.add(msg)
        db.session.commit()
        sa_id, msg_id = sa.id, msg.id

    login(client, 'prot_other')
    resp = client.delete(f'/api/shared/{sa_id}/messages/{msg_id}')
    assert resp.status_code == 403


def test_react_toggle(client):
    from app import SharedAccountMessage, SharedAccountReaction
    with flask_app.app_context():
        u = create_user('react_u1', 'react_u1@test.com')
        sa = make_shared(u)
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=u.id, text='Hi'
        )
        db.session.add(msg)
        db.session.commit()
        sa_id, msg_id = sa.id, msg.id

    login(client, 'react_u1')
    resp = client.post(
        f'/api/shared/{sa_id}/messages/{msg_id}/react',
        data={'emoji': '❤️'}
    )
    assert resp.get_json()['action'] == 'added'

    resp = client.post(
        f'/api/shared/{sa_id}/messages/{msg_id}/react',
        data={'emoji': '❤️'}
    )
    assert resp.get_json()['action'] == 'removed'

    with flask_app.app_context():
        assert SharedAccountReaction.query.filter_by(message_id=msg_id).count() == 0


def test_max_50_messages_enforced(client):
    from app import SharedAccountMessage
    with flask_app.app_context():
        u = create_user('max_u1', 'max_u1@test.com')
        sa = make_shared(u)
        for i in range(50):
            db.session.add(SharedAccountMessage(
                shared_account_id=sa.id, user_id=u.id, text=f'msg {i}'
            ))
        db.session.commit()
        sa_id = sa.id

    login(client, 'max_u1')
    client.post(f'/api/shared/{sa_id}/messages', data={'text': 'msg 51'})

    with flask_app.app_context():
        count = SharedAccountMessage.query.filter_by(shared_account_id=sa_id).count()
        assert count == 50
        latest = (SharedAccountMessage.query
                  .filter_by(shared_account_id=sa_id)
                  .order_by(SharedAccountMessage.created_at.desc())
                  .first())
        assert latest.text == 'msg 51'
