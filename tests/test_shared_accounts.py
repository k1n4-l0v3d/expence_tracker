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
    return client.post('/login', data={'username': username, 'password': password,
                                       'next': ''}, follow_redirects=True)


def test_shared_account_model_creation():
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        u = create_user('owner1', 'owner1@test.com')
        sa = SharedAccount(name='Family Budget', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        m = SharedAccountMember(shared_account_id=sa.id, user_id=u.id)
        db.session.add(m)
        db.session.commit()
        assert SharedAccount.query.filter_by(name='Family Budget').count() == 1
        assert SharedAccountMember.query.filter_by(user_id=u.id).count() == 1


def test_shared_account_cascade_delete():
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        u = create_user('owner2', 'owner2@test.com')
        sa = SharedAccount(name='To Delete', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        db.session.delete(sa)
        db.session.commit()
        assert SharedAccountMember.query.count() == 0


def test_switch_to_shared_context(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        u = create_user('ctx_user', 'ctx@test.com')
        sa = SharedAccount(name='Test Account', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'ctx_user')
    resp = client.get(f'/shared/switch/{sa_id}', follow_redirects=True)
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get('active_shared_account_id') == sa_id


def test_switch_to_personal_context(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        u = create_user('ctx_user2', 'ctx2@test.com')
        sa = SharedAccount(name='Test Account2', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'ctx_user2')
    client.get(f'/shared/switch/{sa_id}')
    client.get('/shared/switch/personal')

    with client.session_transaction() as sess:
        assert sess.get('active_shared_account_id') is None


def test_non_member_switch_rejected(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        owner = create_user('owner_nm', 'owner_nm@test.com')
        create_user('other_nm', 'other_nm@test.com')
        sa = SharedAccount(name='Private', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'other_nm')
    resp = client.get(f'/shared/switch/{sa_id}', follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_create_shared_account(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        create_user('creator1', 'creator1@test.com')
    login(client, 'creator1')

    resp = client.post('/shared/create',
                       data={'name': 'Family Budget'},
                       follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        sa = SharedAccount.query.filter_by(name='Family Budget').first()
        assert sa is not None
        assert SharedAccountMember.query.filter_by(shared_account_id=sa.id).count() == 1


def test_invite_existing_user(client):
    from app import SharedAccount, SharedAccountMember, SharedAccountInvitation
    with flask_app.app_context():
        owner = create_user('inv_owner', 'inv_owner@test.com')
        create_user('inv_target', 'inv_target@test.com')
        sa = SharedAccount(name='Invite Test', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'inv_owner')
    resp = client.post(f'/shared/{sa_id}/invite',
                       data={'identifier': 'inv_target'},
                       follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        # Приглашение создано, но участник ещё не добавлен
        assert SharedAccountMember.query.filter_by(shared_account_id=sa_id).count() == 1
        assert SharedAccountInvitation.query.filter_by(
            shared_account_id=sa_id, status='pending'
        ).count() == 1


def test_invite_accept_adds_member(client):
    from app import SharedAccount, SharedAccountMember, SharedAccountInvitation, User
    with flask_app.app_context():
        owner = create_user('acc_owner', 'acc_owner@test.com')
        invitee = create_user('acc_target', 'acc_target@test.com')
        sa = SharedAccount(name='Accept Test', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        inv = SharedAccountInvitation(
            shared_account_id=sa.id,
            invited_user_id=invitee.id,
            invited_by_user_id=owner.id,
        )
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id
        sa_id = sa.id

    login(client, 'acc_target')
    resp = client.post(f'/invitations/{inv_id}/accept', follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        assert SharedAccountMember.query.filter_by(shared_account_id=sa_id).count() == 2
        assert SharedAccountInvitation.query.get(inv_id).status == 'accepted'


def test_invite_decline_does_not_add_member(client):
    from app import SharedAccount, SharedAccountMember, SharedAccountInvitation, User
    with flask_app.app_context():
        owner = create_user('dec_owner', 'dec_owner@test.com')
        invitee = create_user('dec_target', 'dec_target@test.com')
        sa = SharedAccount(name='Decline Test', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        inv = SharedAccountInvitation(
            shared_account_id=sa.id,
            invited_user_id=invitee.id,
            invited_by_user_id=owner.id,
        )
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id
        sa_id = sa.id

    login(client, 'dec_target')
    resp = client.post(f'/invitations/{inv_id}/decline', follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        assert SharedAccountMember.query.filter_by(shared_account_id=sa_id).count() == 1
        assert SharedAccountInvitation.query.get(inv_id).status == 'declined'


def test_invite_nonexistent_user(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        owner = create_user('inv_owner2', 'inv_owner2@test.com')
        sa = SharedAccount(name='Test2', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'inv_owner2')
    resp = client.post(f'/shared/{sa_id}/invite',
                       data={'identifier': 'nobody_exists'},
                       follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        assert SharedAccountMember.query.filter_by(shared_account_id=sa_id).count() == 1


def test_leave_last_member_deletes_account(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        u = create_user('leaver', 'leaver@test.com')
        sa = SharedAccount(name='Doomed', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'leaver')
    resp = client.post(f'/shared/{sa_id}/leave', follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        assert db.session.get(SharedAccount, sa_id) is None


def test_expense_created_in_shared_context(client):
    from app import SharedAccount, SharedAccountMember, User, Expense, Category
    with flask_app.app_context():
        u = create_user('exp_user', 'exp_user@test.com')
        sa = SharedAccount(name='Exp Account', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        cat = Category(name='Food', color='#ff0000')
        db.session.add(cat)
        db.session.commit()
        sa_id = sa.id
        cat_id = cat.id

    login(client, 'exp_user')
    client.get(f'/shared/switch/{sa_id}')

    resp = client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': '500',
        'description': 'Shared groceries',
        'expense_date': '2024-05-01',
        'is_planned': 'on',
        'is_spent': 'on',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        exp = Expense.query.filter_by(description='Shared groceries').first()
        assert exp is not None
        assert exp.shared_account_id == sa_id
        assert exp.added_by_user_id == User.query.filter_by(username='exp_user').first().id


def test_expense_list_filters_by_context(client):
    from app import SharedAccount, SharedAccountMember, Expense, Category
    from datetime import date as dt
    with flask_app.app_context():
        u = create_user('list_user', 'list_user@test.com')
        sa = SharedAccount(name='List Account', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        cat = Category(name='Transport', color='#0000ff')
        db.session.add(cat)
        db.session.flush()
        db.session.add(Expense(user_id=u.id, category_id=cat.id, amount=100,
                                expense_date=dt(2024, 5, 1), is_planned=True, is_spent=True))
        db.session.add(Expense(user_id=u.id, category_id=cat.id, amount=200,
                                expense_date=dt(2024, 5, 1), is_planned=True, is_spent=True,
                                shared_account_id=sa.id, added_by_user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'list_user')

    resp = client.get('/expenses?year=2024&month=5')
    assert resp.status_code == 200

    client.get(f'/shared/switch/{sa_id}')
    resp = client.get('/expenses?year=2024&month=5')
    assert resp.status_code == 200
