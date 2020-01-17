from selfdrive.config import Conversions as CV
from selfdrive.car.honda.values import HONDA_BOSCH


def get_pt_bus(car_fingerprint, has_relay):
  return 1 if car_fingerprint in HONDA_BOSCH and has_relay else 0


def get_lkas_cmd_bus(car_fingerprint, openpilot_longitudinal_control, has_relay):
  if openpilot_longitudinal_control:
    return get_pt_bus(car_fingerprint, has_relay)
  return 2 if car_fingerprint in HONDA_BOSCH and not has_relay else 0


def create_brake_command(packer, apply_brake, pump_on, pcm_override, pcm_cancel_cmd, fcw, idx, car_fingerprint, has_relay, stock_brake):
  # TODO: do we loose pressure if we keep pump off for long?
  brakelights = apply_brake > 0
  brake_rq = apply_brake > 0
  pcm_fault_cmd = False

  values = {
    "COMPUTER_BRAKE": apply_brake,
    "BRAKE_PUMP_REQUEST": pump_on,
    "CRUISE_OVERRIDE": pcm_override,
    "CRUISE_FAULT_CMD": pcm_fault_cmd,
    "CRUISE_CANCEL_CMD": pcm_cancel_cmd,
    "COMPUTER_BRAKE_REQUEST": brake_rq,
    "SET_ME_1": 1,
    "BRAKE_LIGHTS": brakelights,
    "CHIME": stock_brake["CHIME"] if fcw else 0,  # send the chime for stock fcw
    "FCW": fcw << 1,  # TODO: Why are there two bits for fcw?
    "AEB_REQ_1": 0,
    "AEB_REQ_2": 0,
    "AEB_STATUS": 0,
  }
  bus = get_pt_bus(car_fingerprint, has_relay)
  return packer.make_can_msg("BRAKE_COMMAND", bus, values, idx)


def create_gas_command(packer, gas_amount, idx):
  enable = gas_amount > 0.001

  values = {"ENABLE": enable}

  if enable:
    values["GAS_COMMAND"] = gas_amount * 255.
    values["GAS_COMMAND2"] = gas_amount * 255.

  return packer.make_can_msg("GAS_COMMAND", 0, values, idx)

def create_acc_commands(packer, enabled, accel, idx, v_ego, car_fingerprint, has_relay):
  commands = []
  bus = get_pt_bus(car_fingerprint, has_relay)

  # 0 = off
  # 5 = on
  control_on = 5 if enabled else 0
  # 0 to +2000? = range
  # -30000 = no gas
  gas_command = int(accel * 1000.) if enabled and accel > 0 else -30000
  # -400 to +400 = range
  # 0 = no accel
  accel_command = int(accel * 100.) if enabled else 0
  # 1 = brake
  # 0 = no brake
  braking = 1 if enabled and accel < 0 else 0
  standstill = 1 if enabled and accel < 0 and v_ego <= 0 else 0
  standstill_release = 1 if enabled and accel > 0 and v_ego <= 0 else 0

  acc_control_values = {
    # setting CONTROL_ON causes car to set POWERTRAIN_DATA->ACC_STATUS = 1
    "CONTROL_ON": control_on,
    "GAS_COMMAND": gas_command, # used for gas
    "ACCEL_COMMAND": accel_command, # used for brakes
    "BRAKE_LIGHTS": braking,
    "BRAKE_REQUEST": braking,
    "STANDSTILL": standstill,
    "STANDSTILL_RELEASE": standstill_release,
    # TODO: AEB from vision radar?
    # "AEB_STATUS": ?
    # "AEB_BRAKING": ?
    # "AEB_PREPARE": ?
  }
  commands.append(packer.make_can_msg("ACC_CONTROL", bus, acc_control_values, idx))

  acc_control_on_values = {
    "SET_TO_3": 0x03,
    "CONTROL_ON": enabled,
    "SET_TO_FF": 0xff,
    "SET_TO_75": 0x75,
    "SET_TO_30": 0x30,
  }
  commands.append(packer.make_can_msg("ACC_CONTROL_ON", bus, acc_control_on_values, idx))
  return commands

def create_steering_control(packer, apply_steer, lkas_active, car_fingerprint, openpilot_longitudinal_control, idx, has_relay):

  values = {
    "STEER_TORQUE": apply_steer if lkas_active else 0,
    "STEER_TORQUE_REQUEST": lkas_active,
  }
  bus = get_lkas_cmd_bus(car_fingerprint, openpilot_longitudinal_control, has_relay)
  return packer.make_can_msg("STEERING_CONTROL", bus, values, idx)

def create_ui_commands(packer, pcm_speed, hud, car_fingerprint, openpilot_longitudinal_control, is_metric, idx, has_relay, stock_hud):
  commands = []
  bus_pt = get_pt_bus(car_fingerprint, has_relay)
  bus_lkas = get_lkas_cmd_bus(car_fingerprint, openpilot_longitudinal_control, has_relay)

  if car_fingerprint in HONDA_BOSCH:
    acc_hud_values = {
      'CRUISE_SPEED': hud.v_cruise,
      'ENABLE_MINI_CAR': 1,
      'SET_TO_1': 1,
      'HUD_LEAD': hud.car,
      'HUD_DISTANCE': 3,
      'ACC_ON': hud.car != 0,
      'SET_TO_X1': 1,
      'IMPERIAL_UNIT': int(not is_metric),
    }
  else:
    acc_hud_values = {
      'PCM_SPEED': pcm_speed * CV.MS_TO_KPH,
      'PCM_GAS': hud.pcm_accel,
      'CRUISE_SPEED': hud.v_cruise,
      'ENABLE_MINI_CAR': 1,
      'HUD_LEAD': hud.car,
      'HUD_DISTANCE': 3,    # max distance setting on display
      'IMPERIAL_UNIT': int(not is_metric),
      'SET_ME_X01_2': 1,
      'SET_ME_X01': 1,
      "FCM_OFF": stock_hud["FCM_OFF"],
      "FCM_OFF_2": stock_hud["FCM_OFF_2"],
      "FCM_PROBLEM": stock_hud["FCM_PROBLEM"],
      "ICONS": stock_hud["ICONS"],
    }

  if openpilot_longitudinal_control:
    commands.append(packer.make_can_msg("ACC_HUD", bus_pt, acc_hud_values, idx))

  lkas_hud_values = {
    'SET_ME_X41': 0x41,
    'SET_ME_X48': 0x48,
    'STEERING_REQUIRED': hud.steer_required,
    'SOLID_LANES': hud.lanes,
    'BEEP': 0,
  }
  commands.append(packer.make_can_msg('LKAS_HUD', bus_lkas, lkas_hud_values, idx))

  if car_fingerprint in (CAR.CIVIC, CAR.ODYSSEY):
    radar_hud_values = {
      'ACC_ALERTS': hud.acc_alert,
      'LEAD_SPEED': 0x1fe,  # What are these magic values
      'LEAD_STATE': 0x7,
      'LEAD_DISTANCE': 0x1e,
    }
  elif car_fingerprint in HONDA_BOSCH:
    radar_hud_values = {
      'SET_TO_1' : 0x01,
    }

  if openpilot_longitudinal_control:
    commands.append(packer.make_can_msg('RADAR_HUD', bus_pt, radar_hud_values, idx))
  return commands


def spam_buttons_command(packer, button_val, idx, car_fingerprint, has_relay):
  values = {
    'CRUISE_BUTTONS': button_val,
    'CRUISE_SETTING': 0,
  }
  bus = get_pt_bus(car_fingerprint, has_relay)
  return packer.make_can_msg("SCM_BUTTONS", bus, values, idx)
