"""Staff-only scene ownership layered on the existing bounded launch protocol.

The rotation list is never extended. A staff candidate uses the same cover,
FIRST_FRAME gate and Windows Job cleanup as a normal candidate.
"""
import os
from manager import SceneManager, ConfigurationError, BASE_DIR, validate_scene_entrypoint

STAFF_LABELS = {'minecraft': 'マイクラ風'}

class StaffSceneManager(SceneManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        scenes = {'minecraft': os.path.join(BASE_DIR, 'minecraft_staff_acer.py')}
        for path in scenes.values():
            validate_scene_entrypoint(path)
        self.init_staff_state(scenes)

    def init_staff_state(self, scenes):
        self.staff_scenes = dict(scenes)
        self.staff_mode = 'normal'
        self.staff_error = None
        self.staff_target = None
        self.staff_scene_id = None
        self.return_scene = None
        self.return_index = None
        self.rotation_generation = 0
        self.mode_revision = 0
        self._current_stop_uncertain = False
        self._return_requested = False

    @property
    def staff_locked(self):
        return self.staff_mode != 'normal'

    def _set_mode(self, mode):
        if mode in {'normal', 'blocked', 'recovery_failed'}:
            self._return_requested = False
        if mode != self.staff_mode:
            self.staff_mode = mode
            self.mode_revision += 1

    def request_scene(self, action='next', scene_path=None):
        if self.staff_locked:
            return False
        return super().request_scene(action, scene_path)

    def resume_safe(self):
        # Error recovery owns this cover until every uncertain stop is resolved.
        # Healthy staff play and a completed return may still use normal Safe.
        if self.staff_mode in {'blocked', 'recovery_failed'}:
            return False
        return super().resume_safe()

    def _next_scene_path(self):
        return self.staff_target or super()._next_scene_path()

    def request_staff(self, identifier):
        if identifier not in self.staff_scenes:
            raise ConfigurationError('Unknown staff scene identifier')
        if (self.staff_locked or self.switch_pending or self.transition_busy or self.fatal_error
                or self.running_scene_path not in self.all_scenes or not self.is_scene_running()):
            return False
        self.return_scene = self.running_scene_path
        self.return_index = self.scene_index
        self.staff_error = None
        self.staff_scene_id = identifier
        self.staff_target = self.staff_scenes[identifier]
        self._set_mode('entering')
        if self.preloaded_process is not None and not self._discard_preloaded():
            self.staff_error = 'Preloaded scene could not be stopped'
            self._set_mode('blocked')
            return False
        # Use the existing request path without adding the staff scene to all_scenes.
        return super().request_scene('select', self.return_scene)

    def return_to_rotation(self):
        if self.staff_mode == 'entering':
            # Finish the owned candidate's FIRST_FRAME/reveal before returning.
            self._return_requested = True
            return True
        if self.staff_mode not in {'active', 'recovery_failed', 'blocked'}:
            return False
        if self.transition is not None and self.transition.error:
            # close() retains ownership on failure; never overlap overlays.
            if not self.transition.close():
                self.staff_error = 'Transition could not be stopped; retry return after checking the display'
                self._set_mode('blocked')
                return False
            self.transition = self.transition_process = None
            self.fatal_error = None
        if self.staff_mode == 'blocked':
            if not self._discard_preloaded():
                return False
            if self.uncontained_process is not None:
                if not self._kill_process(self.uncontained_process, 'failed launch', reason='staff_retry'):
                    return False
                self.uncontained_process = None
            # Stop only a predecessor whose own stop was uncertain (or whose
            # launcher exited but may still own descendants). Otherwise retain
            # the healthy normal scene through the retry's FIRST_FRAME gate.
            if self._current_stop_uncertain or not self.is_scene_running():
                if not self.kill_current():
                    return False
                self._current_stop_uncertain = False
            self.fatal_error = None
        held = self.transition is not None and self.transition.holding_cover is True
        if self.transition_busy and not held:
            if self.staff_mode == 'active':
                self._return_requested = True
                return True
            return False
        self.safe_requested = bool(held)
        self.staff_error = None
        self.staff_target = self.return_scene
        self._return_requested = False
        self._set_mode('returning')
        accepted = super().request_scene('select', self.return_scene)
        if not accepted and self.staff_mode == 'returning' and not self.switch_pending:
            self._set_mode('recovery_failed')
        return accepted

    def _ensure_preloaded_scene(self):
        if self.staff_locked and not self.switch_pending:
            return False
        return super()._ensure_preloaded_scene()

    def _fail_switch(self, reason):
        if not self.staff_locked:
            return super()._fail_switch(reason)
        entering = self.staff_mode == 'entering'
        self.staff_error = self.last_switch_error = reason
        self.switch_pending = False
        self.requested_scene_index = None
        self.switch_had_live_scene = False
        stopped = self._discard_preloaded()
        if 'current scene could not be stopped' in reason:
            self._current_stop_uncertain = True
        if not stopped or self.uncontained_process is not None or self._current_stop_uncertain:
            self._set_mode('blocked')
            return
        self.fatal_error = None
        if entering and self.is_scene_running() and self.running_scene_path == self.return_scene:
            self._set_mode('entry_failed')
            if not self.safe_requested and self.transition is not None and self.transition.covered and not self.transition.error:
                self.transition.reveal()
        else:
            self.safe_requested = True
            self._set_mode('recovery_failed')

    def tick(self):
        # Keep the operator panel alive in blocked/error states, retaining every
        # handle until stop succeeds. Never launch on an uncertain stop.
        if self.staff_mode in {'blocked', 'recovery_failed'}:
            if self.transition is not None:
                self.transition.poll()
            return
        before = self.completed_promotions
        mode = self.staff_mode
        super().tick()
        if self.fatal_error and self.staff_locked:
            self.staff_error = self.fatal_error
            self._set_mode('blocked')
            return
        if self.completed_promotions != before and mode in {'entering', 'returning'}:
            self.scene_index = self.return_index
            self.staff_target = None
            self._set_mode('active' if mode == 'entering' else 'return_reveal')
        if self.staff_mode in {'entry_failed', 'return_reveal'} and not self.transition_busy:
            self.staff_target = None
            self.safe_requested = False
            self._set_mode('normal')
            self.rotation_generation += 1
        if (self._return_requested and self.staff_mode == 'active'
                and (not self.transition_busy or
                     (self.transition is not None and self.transition.holding_cover is True))):
            self.return_to_rotation()
        held = self.transition is not None and self.transition.holding_cover is True
        if self.staff_mode == 'active' and not self.is_scene_running() and (not self.transition_busy or held):
            self.return_to_rotation()

    def operator_snapshot(self):
        result = super().operator_snapshot()
        result['staff'] = {'mode': self.staff_mode, 'error': self.staff_error,
                           'return_requested': self._return_requested,
                           'label': STAFF_LABELS.get(self.staff_scene_id, ''),
                           'scenes': [{'id': key, 'label': STAFF_LABELS.get(key, key)} for key in self.staff_scenes],
                           'return_scene': os.path.basename(self.return_scene) if self.return_scene else None}
        result['mode_revision'] = self.mode_revision
        return result
