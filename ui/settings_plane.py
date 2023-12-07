# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui/settings_plane.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_SettingsPlane(object):
    def setupUi(self, SettingsPlane):
        SettingsPlane.setObjectName("SettingsPlane")
        SettingsPlane.resize(228, 367)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(SettingsPlane.sizePolicy().hasHeightForWidth())
        SettingsPlane.setSizePolicy(sizePolicy)
        self.verticalLayout = QtWidgets.QVBoxLayout(SettingsPlane)
        self.verticalLayout.setSizeConstraint(QtWidgets.QLayout.SetDefaultConstraint)
        self.verticalLayout.setContentsMargins(11, 11, 11, 11)
        self.verticalLayout.setObjectName("verticalLayout")
        self.item_name = QtWidgets.QLineEdit(SettingsPlane)
        self.item_name.setObjectName("item_name")
        self.verticalLayout.addWidget(self.item_name)
        self.layout_creation = QtWidgets.QHBoxLayout()
        self.layout_creation.setObjectName("layout_creation")
        self.button_new_plane = QtWidgets.QPushButton(SettingsPlane)
        self.button_new_plane.setObjectName("button_new_plane")
        self.layout_creation.addWidget(self.button_new_plane)
        self.button_delete_plane = QtWidgets.QPushButton(SettingsPlane)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("ui/graphics/icon_trash.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.button_delete_plane.setIcon(icon)
        self.button_delete_plane.setObjectName("button_delete_plane")
        self.layout_creation.addWidget(self.button_delete_plane)
        self.verticalLayout.addLayout(self.layout_creation)
        self.layout_params = QtWidgets.QGridLayout()
        self.layout_params.setSpacing(1)
        self.layout_params.setObjectName("layout_params")
        self.label_z = QtWidgets.QLabel(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_z.sizePolicy().hasHeightForWidth())
        self.label_z.setSizePolicy(sizePolicy)
        self.label_z.setAlignment(QtCore.Qt.AlignCenter)
        self.label_z.setObjectName("label_z")
        self.layout_params.addWidget(self.label_z, 0, 3, 1, 1)
        self.label_y = QtWidgets.QLabel(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_y.sizePolicy().hasHeightForWidth())
        self.label_y.setSizePolicy(sizePolicy)
        self.label_y.setAlignment(QtCore.Qt.AlignCenter)
        self.label_y.setObjectName("label_y")
        self.layout_params.addWidget(self.label_y, 0, 2, 1, 1)
        self.edit_origin_z = QtWidgets.QLineEdit(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.edit_origin_z.sizePolicy().hasHeightForWidth())
        self.edit_origin_z.setSizePolicy(sizePolicy)
        self.edit_origin_z.setMinimumSize(QtCore.QSize(50, 0))
        self.edit_origin_z.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.edit_origin_z.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.edit_origin_z.setObjectName("edit_origin_z")
        self.layout_params.addWidget(self.edit_origin_z, 1, 3, 1, 1)
        self.edit_origin_y = QtWidgets.QLineEdit(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.edit_origin_y.sizePolicy().hasHeightForWidth())
        self.edit_origin_y.setSizePolicy(sizePolicy)
        self.edit_origin_y.setMinimumSize(QtCore.QSize(50, 0))
        self.edit_origin_y.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.edit_origin_y.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.edit_origin_y.setObjectName("edit_origin_y")
        self.layout_params.addWidget(self.edit_origin_y, 1, 2, 1, 1)
        self.label_x = QtWidgets.QLabel(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_x.sizePolicy().hasHeightForWidth())
        self.label_x.setSizePolicy(sizePolicy)
        self.label_x.setAlignment(QtCore.Qt.AlignCenter)
        self.label_x.setObjectName("label_x")
        self.layout_params.addWidget(self.label_x, 0, 1, 1, 1)
        self.edit_normal_z = QtWidgets.QLineEdit(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.edit_normal_z.sizePolicy().hasHeightForWidth())
        self.edit_normal_z.setSizePolicy(sizePolicy)
        self.edit_normal_z.setMinimumSize(QtCore.QSize(50, 0))
        self.edit_normal_z.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.edit_normal_z.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.edit_normal_z.setObjectName("edit_normal_z")
        self.layout_params.addWidget(self.edit_normal_z, 2, 3, 1, 1)
        self.edit_normal_y = QtWidgets.QLineEdit(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.edit_normal_y.sizePolicy().hasHeightForWidth())
        self.edit_normal_y.setSizePolicy(sizePolicy)
        self.edit_normal_y.setMinimumSize(QtCore.QSize(50, 0))
        self.edit_normal_y.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.edit_normal_y.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.edit_normal_y.setObjectName("edit_normal_y")
        self.layout_params.addWidget(self.edit_normal_y, 2, 2, 1, 1)
        self.edit_normal_x = QtWidgets.QLineEdit(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.edit_normal_x.sizePolicy().hasHeightForWidth())
        self.edit_normal_x.setSizePolicy(sizePolicy)
        self.edit_normal_x.setMinimumSize(QtCore.QSize(50, 0))
        self.edit_normal_x.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.edit_normal_x.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.edit_normal_x.setObjectName("edit_normal_x")
        self.layout_params.addWidget(self.edit_normal_x, 2, 1, 1, 1)
        self.label_normal = QtWidgets.QLabel(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_normal.sizePolicy().hasHeightForWidth())
        self.label_normal.setSizePolicy(sizePolicy)
        self.label_normal.setMinimumSize(QtCore.QSize(45, 0))
        self.label_normal.setObjectName("label_normal")
        self.layout_params.addWidget(self.label_normal, 2, 0, 1, 1)
        self.label_origin = QtWidgets.QLabel(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_origin.sizePolicy().hasHeightForWidth())
        self.label_origin.setSizePolicy(sizePolicy)
        self.label_origin.setMinimumSize(QtCore.QSize(45, 0))
        self.label_origin.setObjectName("label_origin")
        self.layout_params.addWidget(self.label_origin, 1, 0, 1, 1)
        self.edit_origin_x = QtWidgets.QLineEdit(SettingsPlane)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.edit_origin_x.sizePolicy().hasHeightForWidth())
        self.edit_origin_x.setSizePolicy(sizePolicy)
        self.edit_origin_x.setMinimumSize(QtCore.QSize(50, 0))
        self.edit_origin_x.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.edit_origin_x.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.edit_origin_x.setObjectName("edit_origin_x")
        self.layout_params.addWidget(self.edit_origin_x, 1, 1, 1, 1)
        self.verticalLayout.addLayout(self.layout_params)
        self.layout_button = QtWidgets.QGroupBox(SettingsPlane)
        self.layout_button.setObjectName("layout_button")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout(self.layout_button)
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 2)
        self.horizontalLayout_3.setSpacing(0)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.button_look_at = QtWidgets.QPushButton(self.layout_button)
        self.button_look_at.setObjectName("button_look_at")
        self.horizontalLayout_3.addWidget(self.button_look_at)
        self.button_normal_to_view = QtWidgets.QPushButton(self.layout_button)
        self.button_normal_to_view.setObjectName("button_normal_to_view")
        self.horizontalLayout_3.addWidget(self.button_normal_to_view)
        self.verticalLayout.addWidget(self.layout_button)
        self.checkbox_save_keyframes = QtWidgets.QCheckBox(SettingsPlane)
        self.checkbox_save_keyframes.setChecked(True)
        self.checkbox_save_keyframes.setObjectName("checkbox_save_keyframes")
        self.verticalLayout.addWidget(self.checkbox_save_keyframes)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)

        self.retranslateUi(SettingsPlane)
        QtCore.QMetaObject.connectSlotsByName(SettingsPlane)

    def retranslateUi(self, SettingsPlane):
        _translate = QtCore.QCoreApplication.translate
        SettingsPlane.setWindowTitle(_translate("SettingsPlane", "Form"))
        self.item_name.setText(_translate("SettingsPlane", "Plane 1"))
        self.button_new_plane.setText(_translate("SettingsPlane", "+ New Plane"))
        self.button_delete_plane.setText(_translate("SettingsPlane", "Delete Plane"))
        self.label_z.setText(_translate("SettingsPlane", "z"))
        self.label_y.setText(_translate("SettingsPlane", "y"))
        self.edit_origin_z.setText(_translate("SettingsPlane", "0"))
        self.edit_origin_y.setText(_translate("SettingsPlane", "0"))
        self.label_x.setText(_translate("SettingsPlane", "x"))
        self.edit_normal_z.setText(_translate("SettingsPlane", "0"))
        self.edit_normal_y.setText(_translate("SettingsPlane", "0"))
        self.edit_normal_x.setText(_translate("SettingsPlane", "0"))
        self.label_normal.setText(_translate("SettingsPlane", "Normal"))
        self.label_origin.setText(_translate("SettingsPlane", "Origin"))
        self.edit_origin_x.setText(_translate("SettingsPlane", "0"))
        self.layout_button.setTitle(_translate("SettingsPlane", "Camera"))
        self.button_look_at.setText(_translate("SettingsPlane", "Look at"))
        self.button_normal_to_view.setText(_translate("SettingsPlane", "Normal to view"))
        self.checkbox_save_keyframes.setText(_translate("SettingsPlane", "Save to keyframes"))
