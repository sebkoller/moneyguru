# -*- coding: utf-8 -*-
# Created By: Virgil Dupras
# Created On: 2010-01-09
# Copyright 2010 Hardcoded Software (http://www.hardcoded.net)
# 
# This software is licensed under the "HS" License as described in the "LICENSE" file, 
# which should be included with this package. The terms are also available at 
# http://www.hardcoded.net/licenses/hs_license

from .base import BaseView

class ProfitView(BaseView):
    def __init__(self, view, document, children):
        BaseView.__init__(self, view, document, children)
        [self.istatement, self.pgraph, self.ipie, self.epie] = children
    
    #--- Public
    def delete_item(self):
        self.istatement.delete()
    
    def new_item(self):
        self.istatement.add_account()
    
    def new_group(self):
        self.istatement.add_account_group()
    
    def show_account(self):
        self.istatement.show_selected_account()
    