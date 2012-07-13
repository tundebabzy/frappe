# Copyright (c) 2012 Web Notes Technologies Pvt Ltd (http://erpnext.com)
# 
# MIT License (MIT)
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT 
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF 
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# 

import webnotes, json
from webnotes.utils import cint

class DocType:
	def __init__(self, doc, doclist):
		self.doc = doc
		self.doclist = doclist

	def autoname(self):
		"""set name as email id"""
		import re
		from webnotes.utils import validate_email_add

		if self.doc.name not in ('Guest','Administrator'):
			self.doc.email = self.doc.email.strip()
			if not validate_email_add(self.doc.email):
				msgprint("%s is not a valid email id" % self.doc.email)
				raise Exception
		
			self.doc.name = self.doc.email

	def validate(self):
		self.validate_max_users()
		self.update_roles()
		self.logout_if_disabled()
		
	def logout_if_disabled(self):
		"""logout if disabled"""
		if cint(self.doc.disabled):
			import webnotes.login_manager
			webnotes.login_manager.logout(self.doc.name)
	
	def validate_max_users(self):
		"""don't allow more than max users if set in conf"""
		import conf
		if hasattr(conf, 'max_users'):
			active_users = webnotes.conn.sql("""select count(*) from tabProfile
				where ifnull(enabled, 0)=1 and docstatus<2
				and name not in ('Administrator', 'Guest')""")[0][0]
			if active_users >= conf.max_users and conf.max_users:
				webnotes.msgprint("""
					You already have <b>%(active_users)s</b> active users, \
					which is the maximum number that you are currently allowed to add. <br /><br /> \
					So, to add more users, you can:<br /> \
					1. <b>Upgrade to the unlimited users plan</b>, or<br /> \
					2. <b>Disable one or more of your existing users and try again</b>""" \
					% {'active_users': active_users}, raise_exception=1)
	
	def update_roles(self):
		"""update roles if set"""		
		if self.doc.fields.get('__temp'):
			roles = json.loads(self.doc.fields['__temp'])
			del self.doc.fields['__temp']

			# remove roles
			webnotes.conn.sql("""delete from tabUserRole where parent='%s' 
				and role in ('%s')""" % (self.doc.name, "','".join(roles['unset_roles'])))

			self.check_one_system_manager()

			# add roles
			user_roles = webnotes.get_roles(self.doc.name)
			for role in roles['set_roles']:
				if not role in user_roles:
					self.add_role(role)

	def add_role(self, role):
		"""add role to Profile"""
		from webnotes.model.doc import Document
		d = Document('UserRole')
		d.role = role
		d.parenttype = 'Profile'
		d.parentfield = 'user_roles'
		d.parent = self.doc.name
		d.save()
			
	def check_one_system_manager(self):
		if not webnotes.conn.sql("""select parent from tabUserRole where role='System Manager'
			and docstatus<2"""):
			webnotes.msgprint("""Cannot un-select as System Manager as there must 
				be atleast one 'System Manager'""", raise_exception=1)
				
	def on_update(self):
		# owner is always name
		webnotes.conn.set(self.doc, 'owner' ,self.doc.name)
		self.update_new_password()

	def update_new_password(self):
		"""update new password if set"""
		if self.doc.new_password:
			webnotes.conn.sql("""insert into __Auth (user, `password`) values (%s, password(%s)) 
				on duplicate key update `password`=password(%s)""", (self.doc.name, 
				self.doc.new_password, self.doc.new_password))
			webnotes.conn.set(self.doc, 'new_password', '')
			webnotes.msgprint("Password updated.")

	def get_fullname(self):
		return (self.doc.first_name or '') + \
			(self.doc.first_name and " " or '') + (self.doc.last_name or '')
			
	def on_rename(self,newdn,olddn):
		tables = webnotes.conn.sql("show tables")
		for tab in tables:
			desc = webnotes.conn.sql("desc `%s`" % tab[0], as_dict=1)
			has_fields = []
			for d in desc:
				if d.get('Field') in ['owner', 'modified_by']:
					has_fields.append(d.get('Field'))
			for field in has_fields:
				webnotes.conn.sql("""\
					update `%s` set `%s`=%s
					where `%s`=%s""" % \
					(tab[0], field, '%s', field, '%s'), (newdn, olddn))
		webnotes.conn.sql("""\
			update `tabProfile` set email=%s
			where name=%s""", (newdn, newdn))
						
@webnotes.whitelist()
def get_all_roles(arg=None):
	"""return all roles"""
	return [r[0] for r in webnotes.conn.sql("""select name from tabRole
		where name not in ('Administrator', 'Guest', 'All') order by name""")]
		
@webnotes.whitelist()
def get_user_roles(arg=None):
	"""get roles for a user"""
	return webnotes.get_roles(webnotes.form_dict['uid'])

@webnotes.whitelist()
def get_perm_info(arg=None):
	"""get permission info"""
	return webnotes.conn.sql("""select parent, permlevel, `read`, `write`, submit,
		cancel, amend from tabDocPerm where role=%s 
		and docstatus<2 order by parent, permlevel""", 
			webnotes.form_dict['role'], as_dict=1)

def send_welcome_mail(email, args):
	"""send welcome mail to user with password and login url"""
	pr = Document('Profile', email)
	from webnotes.utils.email_lib import sendmail_md
	args.update({
		'company': webnotes.conn.get_default('company'),
		'password': args.get('password'),
		'account_url': webnotes.conn.get_value('Website Settings',
			'Website Settings', 'subdomain') or ""
	})
	if not args.get('last_name'): args['last_name'] = ''
	sendmail_md(pr.email, subject="Welcome to ERPNext", msg=welcome_txt % args)

@webnotes.whitelist()
def delete(arg=None):
	"""delete user"""
	webnotes.conn.sql("update tabProfile set enabled=0, docstatus=2 where name=%s", 
		webnotes.form_dict['uid'])
	webnotes.login_manager.logout(user=webnotes.form_dict['uid'])
	
welcome_txt = """
## %(company)s

Dear %(first_name)s %(last_name)s

Welcome!

A new account has been created for you, here are your details:

login-id: %(user)s
password: %(password)s

To login to your new ERPNext account, please go to:

%(account_url)s
"""