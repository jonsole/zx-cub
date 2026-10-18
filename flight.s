; Cub's flight model on the Z80: flight_step is flight.py's `step`, a 25th
; of a second, on the game state, operation for operation, so that
; tests/frames_test.py can hold the two to the same bytes. The comments say
; which line of flight.step each part is.
;
; Every product is a signed number of up to 24 bits times one of up to 16
; (mul), into DE:HL -- each fits 32 bits signed, as flight.py says -- then
; shifted right as Python's >> does, flooring (SHIFTED). The constants are
; flight.py's, from game_gen.s.

; C:H:L = the signed word at `at`.
					MACRO	LOAD_S16 at
					ld		hl,(at)
					ld		a,h
					rla
					sbc		a,a
					ld		c,a
					ENDM

; C:H:L = the unsigned word at `at`.
					MACRO	LOAD_U16 at
					ld		hl,(at)
					ld		c,0
					ENDM

; C:H:L = the 24 bits at `at`.
					MACRO	LOAD_24 at
					ld		hl,(at)
					ld		a,(at + 2)
					ld		c,a
					ENDM

; C:H:L = HL, signed.
					MACRO	WIDEN
					ld		a,h
					rla
					sbc		a,a
					ld		c,a
					ENDM

; The 24 bits at `at` = C:H:L.
					MACRO	STORE_24 at
					ld		(at),hl
					ld		a,c
					ld		(at + 2),a
					ENDM

; DE:HL >>= bits, signed, flooring: whole bytes by moving registers, the
; sign filling in above, then up to four bits right; or for five to seven,
; one to three bits left with the sign as a fifth byte in A, and a byte
; more dropped.
					MACRO	SHIFTED bits
					IF		((bits) & 7) <= 4
					DROP_BYTES	(bits) >> 3
					REPT	(bits) & 7
					sra		d
					rr		e
					rr		h
					rr		l
					EDUP
					ELSE
					ld		a,d
					rla
					sbc		a,a
					REPT	8 - ((bits) & 7)
					add		hl,hl
					rl		e
					rl		d
					rla
					EDUP
					DROP_FROM_A	((bits) >> 3) + 1
					ENDIF
					ENDM

; DE:HL >>= 8 count, signed.
					MACRO	DROP_BYTES count
					IF		(count) == 1
					ld		l,h
					ld		h,e
					ld		e,d
					ld		a,d
					rla
					sbc		a,a
					ld		d,a
					ENDIF
					IF		(count) == 2
					ex		de,hl
					ld		a,h
					rla
					sbc		a,a
					ld		d,a
					ld		e,a
					ENDIF
					IF		(count) == 3
					ld		l,d
					ld		a,d
					rla
					sbc		a,a
					ld		h,a
					ld		d,a
					ld		e,a
					ENDIF
					ENDM

; DE:HL = A:D:E:H:L >> 8 count, signed, A the top byte.
					MACRO	DROP_FROM_A count
					IF		(count) == 1
					ld		l,h
					ld		h,e
					ld		e,d
					ld		d,a
					ENDIF
					IF		(count) == 2
					ld		l,e
					ld		h,d
					ld		e,a
					rla
					sbc		a,a
					ld		d,a
					ENDIF
					IF		(count) == 3
					ld		l,d
					ld		h,a
					rla
					sbc		a,a
					ld		e,a
					ld		d,a
					ENDIF
					ENDM

; The signed byte at `at` moved `pace` a step toward its target, from
; the keys held: the target most if the key more is held, less most if
; less is (flight.toward).
					MACRO	CONTROL at, more, less, most, pace
					ld		de,(state + STATE_KEYS)
					xor		a
					ld		b,a
					ld		a,e
					and		low more
					ld		c,a
					ld		a,d
					and		high more
					or		c
					jr		z,$ + 4
					ld		b,most
					ld		a,e
					and		low less
					ld		c,a
					ld		a,d
					and		high less
					or		c
					ld		a,b
					jr		z,$ + 4
					sub		most
					ld		b,pace
					ld		hl,at
					call	toward
					ENDM

QUARTER_TURN		EQU		16384					; flight.TURN // 4: a sine's angle on, its cosine
COS_LEVEL			EQU		32767					; flight.cos_fine(0): the flight path level

; flight_step: the game state a step on, with the keys at STATE_KEYS held
; (flight.step). Uses everything but IY and the alternate registers.
flight_step:
													; --- the controls ------------------------------------
					ld		a,(state + STATE_THROTTLE)	; throttle
					ld		hl,(state + STATE_KEYS)
					bit		0,l						; THROTTLE_UP
					ASSERT	KEY_THROTTLE_UP == $0001
					jr		z,.no_up
					add		a,THROTTLE_RATE
					jr		nc,.no_up
					ld		a,THROTTLE_FULL
.no_up:
					ASSERT	KEY_THROTTLE_DOWN == $0002
					bit		1,l
					jr		z,.no_down
					sub		THROTTLE_RATE
					jr		nc,.no_down
					xor		a
.no_down:
					ASSERT	THROTTLE_FULL == 255
					ld		(state + STATE_THROTTLE),a
					CONTROL	state + STATE_STICK, KEY_STICK_BACK, KEY_STICK_FORWARD, STICK_FULL, STICK_RATE
					CONTROL	state + STATE_STICK_ROLL, KEY_STICK_RIGHT, KEY_STICK_LEFT, STICK_FULL, STICK_RATE
					CONTROL	state + STATE_RUDDER, KEY_RUDDER_RIGHT, KEY_RUDDER_LEFT, RUDDER_FULL, RUDDER_RATE
					ld		a,(state + STATE_KEYS)	; the brakes: held, or parked
					ASSERT	KEY_BRAKES < $100
					and		low KEY_BRAKES
					ld		(f_braking),a
					jr		z,.brakes_done
					ld		a,(state + STATE_FLAGS)
					and		~PARKED
					ld		(state + STATE_FLAGS),a
.brakes_done:
					ld		a,(state + STATE_FLAGS)
					and		PARKED
					ld		hl,f_braking
					or		(hl)
					ld		(hl),a

													; --- the engine --------------------------------------
					ld		hl,(state + STATE_SPEED)	; v16 = speed >> 4
					ld		a,(state + STATE_SPEED + 2)
					REPT	4
					srl		a
					rr		h
					rr		l
					EDUP
					ld		(f_v16),hl
					LOAD_U16	f_v16				; full = STATIC - IDLE +
					ld		de,K_RPM_SPEED			; ((v16 K_RPM_SPEED) >> 16)
					call	mul
					SHIFTED	16
					ld		de,STATIC_RPM - IDLE_RPM
					add		hl,de
					ld		c,0						; target = IDLE + ((full (throttle
					ld		a,(state + STATE_THROTTLE)	; + throttle >> 7)) >> 8)
					ld		e,a
					rlca
					and		1
					add		a,e
					ld		e,a
					ld		a,0
					adc		a,0
					ld		d,a
					call	mul
					SHIFTED	8
					ld		de,IDLE_RPM
					add		hl,de
					ld		de,(state + STATE_RPM)	; rpm += (target - rpm) >> RPM_LAG
					or		a
					sbc		hl,de
					REPT	RPM_LAG
					sra		h
					rr		l
					EDUP
					add		hl,de
					ld		(state + STATE_RPM),hl
					LOAD_U16	state + STATE_RPM	; r = (rpm R_SCALE) >> R_SHIFT
					ld		de,R_SCALE
					call	mul
					SHIFTED	R_SHIFT
					ld		(f_r),hl
					LOAD_U16	f_r					; r r
					ld		de,(f_r)
					call	mul
					SHIFTED	0
					ld		(f_rr),hl
					ld		a,e
					ld		(f_rr + 2),a

													; --- the air -----------------------------------------
					LOAD_U16	f_v16				; q = (v16 v16) >> 12
					ld		de,(f_v16)
					call	mul
					SHIFTED	12
					ld		(f_q),hl
					ld		a,e
					ld		(f_q + 2),a
					ld		hl,0					; gamma: 0 on the ground
					ld		a,(state + STATE_FLAGS)
					and		GROUND
					jr		nz,.level
					ld		hl,(state + STATE_GAMMA + 1)	; gamma >> 8
.level:
					ld		(f_gamma8),hl
					ex		de,hl					; alpha = pitch - (gamma >> 8)
					ld		hl,(state + STATE_PITCH)	; + INCIDENCE
					or		a
					sbc		hl,de
					ld		de,INCIDENCE
					add		hl,de
					ld		(f_alpha),hl
					call	lift_coefficient
					ld		(f_cl),hl
					WIDEN							; cd = CD0 + ((cl cl INDUCED) >> 22)
					ld		de,(f_cl)
					call	mul
					SHIFTED	0
					ld		c,e
					ld		de,INDUCED
					call	mul
					SHIFTED	22
					ld		de,CD0
					add		hl,de
					ld		(f_cd),hl
					LOAD_24	f_q						; qk = (q K_AERO) >> 12
					ld		de,K_AERO
					call	mul
					SHIFTED	12
					ld		(f_qk),hl
					LOAD_U16	f_qk				; lift = (qk cl) >> 12
					ld		de,(f_cl)
					call	mul
					SHIFTED	12
					ld		(f_lift),hl
					LOAD_U16	f_qk				; drag = (qk cd) >> 12
					ld		de,(f_cd)
					call	mul
					SHIFTED	12
					ld		(f_drag),hl
					ld		hl,K_THRUST				; thrust = (((r r >> 2) K_THRUST)
					ld		c,0						; >> 16) - ((((v16 r) >> 8) K_FALL) >> 16)
					ld		de,(f_rr)
					ld		a,(f_rr + 2)
					srl		a
					rr		d
					rr		e
					srl		a
					rr		d
					rr		e
					call	mul
					SHIFTED	16
					ld		(f_thrust),hl
					LOAD_U16	f_v16
					ld		de,(f_r)
					call	mul
					SHIFTED	8
					ld		c,e
					ld		de,K_FALL
					call	mul
					SHIFTED	16
					ex		de,hl
					ld		hl,(f_thrust)
					or		a
					sbc		hl,de
					ld		(f_thrust),hl

					ld		a,(state + STATE_FLAGS)
					and		GROUND
					jp		z,air

													; --- on the ground ------------------------------------
					ld		hl,G_TICK				; load = max(0, G_TICK - lift)
					ld		de,(f_lift)
					or		a
					sbc		hl,de
					jp		p,.loaded
					ld		hl,0
.loaded:
					ld		c,0						; friction = (load (ROLLING +
					ld		de,ROLLING				; BRAKING if braking)) >> 8
					ld		a,(f_braking)
					or		a
					jr		z,.rolling
					ld		de,ROLLING + BRAKING
.rolling:
					call	mul
					SHIFTED	8
					ex		de,hl					; speed += (thrust - drag - friction)
					ld		hl,(f_thrust)			; << STEP_SHIFT
					ld		bc,(f_drag)
					or		a
					sbc		hl,bc
					or		a
					sbc		hl,de
					call	add_speed
					LOAD_U16	f_v16				; heading += (rudder v16 K_STEER)
													; >> (20 - STEP_SHIFT)
					ld		a,(state + STATE_RUDDER)
					ld		e,a
					rla
					sbc		a,a
					ld		d,a
					call	mul
					SHIFTED	0
					ld		c,e
					ld		de,K_STEER
					call	mul
					SHIFTED	20 - STEP_SHIFT
					ld		de,(state + STATE_HEADING)
					add		hl,de
					ld		(state + STATE_HEADING),hl
					call	tail					; pitch = tail(pitch, stick, q, r)
					ld		hl,G_TICK				; lift-off, if lift > G_TICK
					ld		de,(f_lift)
					or		a
					sbc		hl,de
					jp		p,.on_ground
					ld		a,(state + STATE_FLAGS)
					and		~GROUND
					ld		(state + STATE_FLAGS),a
.on_ground:
					ld		hl,0					; gamma, 0 on the ground
					ld		(state + STATE_GAMMA),hl
					xor		a
					ld		(state + STATE_GAMMA + 2),a
					jp		position

; --- in the air ---------------------------------------------------------
; air: flight_step's part in the air, from the stall to the bank.
air:
					ld		hl,ALPHA_STALL			; stalled past ALPHA_STALL, until
					ld		de,(f_alpha)			; under ALPHA_RECOVER
					call	compare
					jr		nc,.not_past
					ld		a,(state + STATE_FLAGS)
					or		STALLED
					ld		(state + STATE_FLAGS),a
					jr		.stall_done
.not_past:
					ld		hl,(f_alpha)
					ld		de,ALPHA_RECOVER
					call	compare
					jr		nc,.stall_done
					ld		a,(state + STATE_FLAGS)
					and		~STALLED
					ld		(state + STATE_FLAGS),a
.stall_done:
					ld		hl,(f_gamma8)			; speed += (thrust - drag - ((G_TICK
					call	sin_fine				; sin(gamma >> 8)) >> 15)) << STEP_SHIFT
					ex		de,hl
					WIDEN
					ld		de,G_TICK
					call	mul
					SHIFTED	15
					ex		de,hl
					ld		hl,(f_thrust)
					ld		bc,(f_drag)
					or		a
					sbc		hl,bc
					or		a
					sbc		hl,de
					call	add_speed
					ld		hl,(f_v16)				; per_speed = K_PER_SPEED /
					ld		de,V16_FLOOR			; max(v16, V16_FLOOR)
					or		a
					sbc		hl,de
					add		hl,de					; carry: v16 under the floor
					jr		c,.slow
					ex		de,hl
.slow:
					call	per_speed_divide
					ld		(f_per_speed),hl
					ld		hl,(state + STATE_BANK)	; across = ((lift cos(bank)) >> 15)
					ld		de,QUARTER_TURN			; - ((G_TICK cos(gamma >> 8)) >> 15)
					add		hl,de
					call	sin_fine
					LOAD_S16	f_lift
					call	mul
					SHIFTED	15
					ld		(f_across),hl
					ld		hl,(f_gamma8)
					ld		de,QUARTER_TURN
					add		hl,de
					call	sin_fine
					ex		de,hl
					WIDEN
					ld		de,G_TICK
					call	mul
					SHIFTED	15
					ex		de,hl
					ld		hl,(f_across)
					or		a
					sbc		hl,de
					ld		de,ACROSS_LIMIT			; held to +-ACROSS_LIMIT
					call	hold
					ld		(f_across),hl
					LOAD_U16	f_per_speed			; gamma += (across per_speed)
					ld		de,(f_across)			; >> (8 - STEP_SHIFT)
					call	mul
					SHIFTED	8 - STEP_SHIFT
					ld		a,(state + STATE_GAMMA)
					add		a,l
					ld		l,a
					ld		a,(state + STATE_GAMMA + 1)
					adc		a,h
					ld		h,a
					ld		a,(state + STATE_GAMMA + 2)
					adc		a,e
					ld		c,a
					call	hold_gamma
					STORE_24	state + STATE_GAMMA
					ld		hl,(state + STATE_BANK)	; sideways = (lift sin(bank)) >> 15
					call	sin_fine
					LOAD_S16	f_lift
					call	mul
					SHIFTED	15
					ex		de,hl
					LOAD_U16	f_per_speed			; heading += (sideways per_speed
					call	mul						; + ($8000 >> STEP_SHIFT))
					ld		bc,$8000 >> STEP_SHIFT	; >> (16 - STEP_SHIFT)
					add		hl,bc
					jr		nc,$ + 3
					inc		de
					SHIFTED	16 - STEP_SHIFT
					ld		de,(state + STATE_HEADING)
					add		hl,de
					ld		(state + STATE_HEADING),hl
					ld		a,(state + STATE_STICK)	; pitch += ((stick AIR_PITCH_RATE)
					ld		l,a						; >> 6) - STALL_PITCH_RATE if stalled
					rla
					sbc		a,a
					ld		h,a
					WIDEN
					ld		de,AIR_PITCH_RATE
					call	mul
					SHIFTED	6
					ld		de,(state + STATE_PITCH)
					add		hl,de
					ld		a,(state + STATE_FLAGS)
					and		STALLED
					jr		z,.flying
					ld		de,STALL_PITCH_RATE
					or		a
					sbc		hl,de
.flying:
					ld		(state + STATE_PITCH),hl
					ld		a,(state + STATE_STICK_ROLL)	; bank += (stick_roll ROLL_RATE)
					ld		l,a						; >> 6, held to +-BANK_LIMIT
					rla
					sbc		a,a
					ld		h,a
					WIDEN
					ld		de,ROLL_RATE
					call	mul
					SHIFTED	6
					ld		de,(state + STATE_BANK)
					add		hl,de
					ld		de,BANK_LIMIT
					call	hold
					ld		(state + STATE_BANK),hl

; --- where it goes ------------------------------------------------------
; position: flight_step's last part, the Cub moved along its path, and put
; back on the ground if it went through it. f_gamma8 is the new gamma's
; angle from here on.
position:
					ld		hl,(state + STATE_SPEED)	; speed8 = speed >> 3, 16 bits
					ld		a,(state + STATE_SPEED + 2)
					REPT	3
					srl		a
					rr		h
					rr		l
					EDUP
					ld		(f_speed8),hl
					ld		hl,(state + STATE_GAMMA + 1)	; along = (speed8 cos(gamma >> 8))
					ld		(f_gamma8),hl			; >> 15
					ld		a,h
					or		l
					jr		nz,.climbing
					ld		hl,(f_speed8)			; level, cos is 32,767: speed8 -
					ld		de,COS_LEVEL			; ((speed8 + 32767) >> 15)
					add		hl,de
					ld		a,0
					adc		a,a
					add		hl,hl
					rla								; A = (speed8 + 32767) >> 15
					ld		e,a
					ld		d,0
					ld		hl,(f_speed8)
					or		a
					sbc		hl,de
					ld		e,0
					jr		.along
.climbing:
					ld		de,QUARTER_TURN
					add		hl,de
					call	sin_fine
					LOAD_U16	f_speed8
					call	mul
					SHIFTED	15
.along:
					ld		(f_along),hl
					ld		a,e
					ld		(f_along + 2),a
					ld		hl,(state + STATE_HEADING)	; x += (along sin(heading))
					call	sin_fine				; >> (12 - STEP_SHIFT): a step's
					LOAD_24	f_along					; ticks' way, along in eights
					call	mul
					SHIFTED	12 - STEP_SHIFT
					ld		ix,state + STATE_X
					call	add_position
					ld		hl,(state + STATE_HEADING)	; z += (along cos(heading))
					ld		de,QUARTER_TURN			; >> (12 - STEP_SHIFT)
					add		hl,de
					call	sin_fine
					LOAD_24	f_along
					call	mul
					SHIFTED	12 - STEP_SHIFT
					ld		ix,state + STATE_Z
					call	add_position
					ld		hl,(f_gamma8)			; y += (speed8 sin(gamma >> 8))
					ld		a,h						; >> (12 - STEP_SHIFT); level, sin
					or		l						; is 0: no change
					jr		z,.not_below
					call	sin_fine
					LOAD_U16	f_speed8
					call	mul
					SHIFTED	12 - STEP_SHIFT
					ld		ix,state + STATE_Y
					call	add_position			; carry: y went below 0
					jr		nc,.not_below
					ld		hl,0					; the Cub on the ground: y below 0
					ld		(state + STATE_Y),hl
					ld		(state + STATE_Y + 2),hl
					ld		a,1
					jr		.ground_check
.not_below:
					ld		hl,(state + STATE_Y)	; or at 0
					ld		de,(state + STATE_Y + 2)
					ld		a,h
					or		l
					or		d
					or		e
					ret		nz
.ground_check:										; A non-zero: y was below 0
					ld		b,a
					ld		a,(state + STATE_FLAGS)
					and		GROUND
					ret		nz						; already on the ground
					ld		a,b
					or		a
					jr		nz,.touchdown
					ld		a,(state + STATE_GAMMA + 2)	; or at 0 with the path down
					rla
					ret		nc
.touchdown:
					xor		a						; back on the ground: gamma and
					ld		(state + STATE_GAMMA),a	; bank 0, on the ground and not
					ld		(state + STATE_GAMMA + 1),a	; stalled, and the pitch between
					ld		(state + STATE_GAMMA + 2),a	; level and three-point
					ld		(state + STATE_BANK),a
					ld		(state + STATE_BANK + 1),a
					ld		a,(state + STATE_FLAGS)
					or		GROUND
					and		~STALLED
					ld		(state + STATE_FLAGS),a
					ld		hl,(state + STATE_PITCH)
					ld		de,THREE_POINT
					call	compare_min
					ld		de,TAIL_UP_LIMIT
					call	compare_max
					ld		(state + STATE_PITCH),hl
					ret

; ---------------------------------------------------------------------------
; tail: flight.tail, the pitch on the ground. Uses everything but IX, IY
; and the alternate registers.
tail:
					LOAD_24	f_rr					; air = q + ((Q_WASH r r) >> 16)
					ld		de,Q_WASH
					call	mul
					SHIFTED	16
					ld		de,(f_q)
					add		hl,de
					ld		a,(f_q + 2)
					adc		a,0
					ld		c,a
					STORE_24	f_air
					ld		a,(state + STATE_STICK)	; term = pitch - ((stick ELEVATOR) >> 6)
					ld		l,a
					rla
					sbc		a,a
					ld		h,a
					WIDEN
					ld		de,ELEVATOR
					call	mul
					SHIFTED	6
					ex		de,hl
					ld		hl,(state + STATE_PITCH)
					or		a
					sbc		hl,de
					ex		de,hl					; moment = air term - TAIL_LOAD
					LOAD_24	f_air
					call	mul
					SHIFTED	0
					ld		bc,TAIL_LOAD & $FFFF
					or		a
					sbc		hl,bc
					ex		de,hl
					ld		bc,TAIL_LOAD >> 16
					sbc		hl,bc					; HL:DE = the moment
					ld		(f_moment),de
					ld		(f_moment + 2),hl
					ld		a,h
					or		l
					or		d
					or		e
					jr		z,.held					; 0: no change
					bit		7,h
					jr		nz,.down
					call	moment_step				; > 0: pitch -= min(PITCH_RATE,
					ex		de,hl					; (moment >> 15) + 1)
					ld		hl,(state + STATE_PITCH)
					or		a
					sbc		hl,de
					jr		.hold
.down:
					ld		hl,(state + STATE_PITCH)	; < 0, the tail up: pitch +=
					ld		de,THREE_POINT			; min(PITCH_RATE, (-moment >> 15) + 1)
					call	compare
					jr		nc,.held
					ld		hl,(f_moment)
					ld		de,(f_moment + 2)
					xor		a
					sub		l
					ld		l,a
					ld		a,0
					sbc		a,h
					ld		h,a
					ld		a,0
					sbc		a,e
					ld		e,a
					ld		a,0
					sbc		a,d
					ld		d,a
					ld		(f_moment),hl
					ld		(f_moment + 2),de
					call	moment_step
					ld		de,(state + STATE_PITCH)
					add		hl,de
.hold:
					ld		de,THREE_POINT			; between level and three-point
					call	compare_min
					ld		de,TAIL_UP_LIMIT
					call	compare_max
					ld		(state + STATE_PITCH),hl
					ret
.held:
					ld		hl,(state + STATE_PITCH)
					jr		.hold

; HL = min(PITCH_RATE, (f_moment >> TAIL_SHIFT) + 1), f_moment positive.
; Uses AF, DE, HL.
moment_step:
					ld		hl,(f_moment)
					ld		de,(f_moment + 2)
					SHIFTED	TAIL_SHIFT
					ld		a,d						; at least PITCH_RATE - 1: PITCH_RATE
					or		e
					jr		nz,.most
					ld		de,PITCH_RATE - 1
					or		a
					sbc		hl,de
					add		hl,de
					jr		nc,.most
					inc		hl
					ret
.most:
					ld		hl,PITCH_RATE
					ret

; ---------------------------------------------------------------------------
; lift_coefficient: HL = flight.lift_coefficient(f_alpha). Uses everything
; but IX, IY and the alternate registers.
lift_coefficient:
					ld		hl,ALPHA_STALL
					ld		de,(f_alpha)
					call	compare					; carry: ALPHA_STALL < alpha
					jr		c,.past
					ld		de,ALPHA_ZERO			; ((alpha - ALPHA_ZERO) CL_SLOPE)
					ld		hl,(f_alpha)			; >> CL_SLOPE_SHIFT
					or		a
					sbc		hl,de
					WIDEN
					ld		de,CL_SLOPE
					call	mul
					SHIFTED	CL_SLOPE_SHIFT
					jr		.held
.past:
					ld		hl,(f_alpha)			; CL_MAX - (((alpha - ALPHA_STALL)
					ld		de,ALPHA_STALL			; CL_SLOPE) >> (CL_SLOPE_SHIFT + 1))
					or		a
					sbc		hl,de
					WIDEN
					ld		de,CL_SLOPE
					call	mul
					SHIFTED	CL_SLOPE_SHIFT + 1
					ex		de,hl
					ld		hl,CL_MAX
					or		a
					sbc		hl,de
.held:
					ld		de,CL_MAX				; held to +-CL_MAX
					jp		hold

; ---------------------------------------------------------------------------
; Speed, angles and positions.

; sin_fine: DE = flight.sin_fine(HL): SINE_FINE at the nearest of its 1,024
; angles. Uses AF, DE, HL.
sin_fine:
					ASSERT	SINE_STEPS == 1024 && SINE_SHIFT == 6
					ld		de,1 << (SINE_SHIFT - 1)	; to the nearest
					add		hl,de
					ld		a,l						; HL = (angle >> 6) words in:
					and		$C0						; angle >> 5, its lowest bit
					ld		l,a						; clear
					REPT	5
					srl		h
					rr		l
					EDUP
					ld		de,sine_fine
					add		hl,de
					ld		e,(hl)
					inc		hl
					ld		d,(hl)
					ret

; speed = min(SPEED_LIMIT, max(0, speed + (HL << STEP_SHIFT))), HL signed.
; Uses AF, C, DE, HL.
add_speed:
					REPT	STEP_SHIFT
					add		hl,hl
					EDUP
					WIDEN
					ld		de,(state + STATE_SPEED)
					add		hl,de
					ld		a,(state + STATE_SPEED + 2)
					adc		a,c
					ld		c,a
					jp		m,.stopped				; below 0
					ld		de,SPEED_LIMIT & $FFFF	; past the limit?
					or		a
					sbc		hl,de
					ld		a,c
					sbc		a,SPEED_LIMIT >> 16
					jr		c,.under
					ld		hl,SPEED_LIMIT & $FFFF
					ld		c,SPEED_LIMIT >> 16
					jr		.store
.under:
					add		hl,de
.store:
					STORE_24	state + STATE_SPEED
					ret
.stopped:
					ld		hl,0
					ld		c,0
					jr		.store

; The 32 bits at IX += DE:HL, signed (a 25-bit move). Carry if the sum is
; below 0, as Python's unbounded sum would be (the y's test); the 32 bits
; are kept all the same, wrapped. Uses AF.
add_position:
					ld		a,(ix + 0)
					add		a,l
					ld		(ix + 0),a
					ld		a,(ix + 1)
					adc		a,h
					ld		(ix + 1),a
					ld		a,(ix + 2)
					adc		a,e
					ld		(ix + 2),a
					ld		a,(ix + 3)
					adc		a,d
					ld		(ix + 3),a
					ccf								; with the move negative, no carry
					ret		nc						; out means the sum is negative
					bit		7,d						; carry now: no carry out. Below
					scf								; zero only if the move is
					ret		nz						; negative
					or		a
					ret

; gamma (C:H:L) held to +-GAMMA_LIMIT. Uses AF, DE.
hold_gamma:
					bit		7,c
					jr		nz,.negative
					ld		de,GAMMA_LIMIT & $FFFF
					or		a
					sbc		hl,de
					ld		a,c
					sbc		a,GAMMA_LIMIT >> 16
					jr		c,.under
					ld		hl,GAMMA_LIMIT & $FFFF
					ld		c,GAMMA_LIMIT >> 16
					ret
.under:
					add		hl,de
					ret
.negative:
					ld		de,-GAMMA_LIMIT & $FFFF
					or		a
					sbc		hl,de
					ld		a,c
					sbc		a,(-GAMMA_LIMIT >> 16) & $FF
					jr		nc,.over
					ld		hl,-GAMMA_LIMIT & $FFFF
					ld		c,(-GAMMA_LIMIT >> 16) & $FF
					ret
.over:
					add		hl,de
					ret

; ---------------------------------------------------------------------------
; Comparisons, signed 16 bits.

; Carry if HL < DE. Keeps HL and DE; uses AF.
compare:
					ld		a,h
					xor		d
					jp		m,.signs				; different signs: HL < DE if HL
					push	hl						; is the negative one
					or		a
					sbc		hl,de
					pop		hl
					ret
.signs:
					ld		a,h
					rla
					ret

; HL = min(HL, DE). Uses AF, DE.
compare_min:
					call	compare
					ret		c
					ex		de,hl
					ret

; HL = max(HL, DE). Uses AF, DE.
compare_max:
					call	compare
					ret		nc
					ex		de,hl
					ret

; HL held to +-DE, DE positive. Uses AF, DE.
hold:
					push	de
					call	compare_min
					pop		de
					push	hl
					ld		hl,0
					or		a
					sbc		hl,de
					ex		de,hl
					pop		hl
					jp		compare_max

; The signed byte at HL = toward(it, A, B) (flight.toward): B nearer A,
; and no further. Both are within +-64, so with 128 added they compare as
; unsigned bytes, and B more or less stays within a byte. Uses AF, DE.
toward:
					xor		$80
					ld		e,a						; E = the target + 128
					ld		a,(hl)
					xor		$80						; A = the value + 128
					cp		e
					jr		z,.done
					jr		c,.below
					sub		b						; above: max(value - rate, target)
					cp		e
					jr		nc,.done
					ld		a,e
					jr		.done
.below:
					add		a,b						; below: min(value + rate, target)
					cp		e
					jr		c,.done
					ld		a,e
.done:
					xor		$80
					ld		(hl),a
					ret

; ---------------------------------------------------------------------------
; The arithmetic.

; mul: DE:HL = C:H:L times DE, signed 24 by signed 16 bits, the product
; within 32 bits signed. The magnitudes multiply by umul16: two 16-bit ones
; with the smaller as the multiplier, so that it takes fewer rounds; a
; 24-bit one as its low 16 bits times |DE|, and its top 8 times |DE| 16
; bits up (of which only the low 16 bits can matter). Uses everything but
; IX, IY and the alternate registers.
mul:
					ld		a,c
					or		d
					jp		p,.positive				; both positive: no signs to mind
					ld		a,c
					xor		d
					ld		(mul_sign),a
					bit		7,c						; |C:H:L|
					jr		z,.x_size
					xor		a
					sub		l
					ld		l,a
					ld		a,0
					sbc		a,h
					ld		h,a
					ld		a,0
					sbc		a,c
					ld		c,a
.x_size:
					bit		7,d						; |DE|
					jr		z,.y_size
					xor		a
					sub		e
					ld		e,a
					ld		a,0
					sbc		a,d
					ld		d,a
.y_size:
					call	.magnitudes
					ld		a,(mul_sign)
					or		a
					ret		p
					xor		a						; negative: DE:HL = -DE:HL
					sub		l
					ld		l,a
					ld		a,0
					sbc		a,h
					ld		h,a
					ld		a,0
					sbc		a,e
					ld		e,a
					ld		a,0
					sbc		a,d
					ld		d,a
					ret
.positive:
.magnitudes:
					ld		a,c
					or		a
					jr		nz,.wide
					push	hl						; 16 by 16: the smaller multiplies
					sbc		hl,de
					pop		hl
					jr		nc,.ordered
					ex		de,hl
.ordered:
					ld		b,h
					ld		c,l
					jp		umul16
.wide:
					ld		(mul_top),a
					ld		(mul_y),de
					ld		b,h
					ld		c,l
					call	umul16					; the low 16 bits times |Y|
					push	hl
					push	de
					ld		a,(mul_top)				; and the top 8 times |Y|, 16 up
					ld		e,a
					ld		d,0
					ld		bc,(mul_y)
					call	umul16
					pop		de
					add		hl,de
					ex		de,hl
					pop		hl
					ret

; HL = A times the register y (B or C, kept), unsigned bytes, by quarter
; squares: f(x + y) - f(|x - y|), f(n) = n n / 4 from SQUARES_LOW, its
; low bytes over two pages, page-aligned, and its high bytes the two pages
; above. Uses AF, DE, HL.
					MACRO	MUL8 y
					ld		e,a
					sub		y
					jr		nc,$ + 4
					neg
					ld		l,a						; |x - y|
					ld		a,e
					add		a,y						; x + y, its ninth bit in the carry
					ld		e,a
					ld		a,high SQUARES_LOW
					adc		a,0
					ld		d,a
					ld		h,high SQUARES_LOW
					ld		a,(de)
					sub		(hl)
					ld		(mul8_low),a
					inc		d						; the high bytes, two pages up
					inc		d						; (the borrow kept)
					inc		h
					inc		h
					ld		a,(de)
					sbc		a,(hl)
					ld		h,a
					ld		a,(mul8_low)
					ld		l,a
					ENDM

; umul16: DE:HL = BC times DE, unsigned. A multiplier under 12 bits by
; shift and add, MSB first from its highest set bit; a wider one by quarter
; squares, four bytes' products, at about 830 T-states whatever they are.
; Uses AF, BC, DE, HL.
umul16:
					ld		hl,0
					ld		a,d
					or		a
					jp		z,.byte
					cp		8						; under 12 bits: shift and add is
					jp		c,.short				; the quicker
					ld		(mul8_d),a				; the multiplier's bytes, D and E
					ld		a,e						; free for MUL8
					ld		(mul8_e),a
					ld		a,(mul8_d)				; B D, 16 bits up
					MUL8	b
					ld		(mul8_high),hl
					ld		a,(mul8_d)				; C D and B E, 8 up
					MUL8	c
					push	hl
					ld		a,(mul8_e)
					MUL8	b
					push	hl
					ld		a,(mul8_e)				; C E
					MUL8	c
					pop		bc						; HL = C E, BC = B E, (SP) = C D
					ex		de,hl
					pop		hl
					add		hl,bc					; HL = the middle, B = its 17th bit
					ld		a,0
					adc		a,a
					ld		b,a
					ld		c,h
					ld		a,d						; D:E = C E with the middle's low
					add		a,l						; byte in its high byte
					ld		d,a
					ld		hl,(mul8_high)			; HL = B D + the middle's high
					ld		a,c						; byte and 17th bit, and the carry
					adc		a,l
					ld		l,a
					ld		a,h
					adc		a,b
					ld		h,a
					ex		de,hl
					ret
.short:
					REPT	5						; D under 8: its top five bits
					sla		e						; clear, skipped at once
					rl		d
					EDUP
					ld		a,11					; the rounds left
.top:
					dec		a
					sla		e						; the top bit out: the first set
					rl		d						; one starts HL at BC
					jr		nc,.top
					ld		h,b
					ld		l,c
.bit:
					add		hl,hl
					rl		e
					rl		d
					jr		nc,.next
					add		hl,bc
					jr		nc,.next
					inc		de
.next:
					dec		a
					jr		nz,.bit
					ret
.byte:
					ld		a,e						; DE under 256: E's 8 bits, with
					or		a						; E the product's top byte and D
					ret		z						; the rounds left (0 at the end);
					ld		e,d						; 0 at once
					ld		d,8
					cp		16						; under 16: its top four bits
					jr		nc,.byte_top			; skipped at once
					add		a,a
					add		a,a
					add		a,a
					add		a,a
					ld		d,4
.byte_top:
					add		a,a
					jr		c,.byte_first
					dec		d
					jr		nz,.byte_top
					ret								; nothing set: 0
.byte_first:
					ld		h,b
					ld		l,c
					dec		d
					ret		z
.byte_bit:
					add		hl,hl
					rl		e
					add		a,a
					jr		nc,.byte_next
					add		hl,bc
					jr		nc,.byte_next
					inc		e
.byte_next:
					dec		d
					jr		nz,.byte_bit
					ret

; per_speed_divide: HL = K_PER_SPEED / DE, unsigned, DE at least
; V16_FLOOR, so that the quotient fits 16 bits: the remainder starts as
; K_PER_SPEED's top 16 bits, and the low 16 come in a bit at a time. Uses
; AF, BC, DE, HL.
per_speed_divide:
					ASSERT	(K_PER_SPEED >> 16) < V16_FLOOR
					ld		hl,K_PER_SPEED >> 16	; the remainder
					ld		bc,K_PER_SPEED & $FFFF	; the bits still to come in,
					ld		a,16					; where the quotient goes out
.bit:
					sla		c
					rl		b
					adc		hl,hl
					or		a
					sbc		hl,de
					jr		nc,.fits
					add		hl,de
					jr		.next
.fits:
					inc		c
.next:
					dec		a
					jr		nz,.bit
					ld		h,b
					ld		l,c
					ret

mul_sign:			DB		0
mul8_low:			DB		0
mul8_d:				DB		0
mul8_e:				DB		0
mul8_high:			DW		0
mul_top:			DB		0
mul_y:				DW		0
f_braking:			DB		0
f_v16:				DW		0
f_r:				DW		0
f_rr:				DS		3
f_q:				DS		3
f_gamma8:			DW		0
f_alpha:			DW		0
f_cl:				DW		0
f_cd:				DW		0
f_qk:				DW		0
f_speed8:			DW		0
f_lift:				DW		0
f_drag:				DW		0
f_thrust:			DW		0
f_per_speed:		DW		0
f_across:			DW		0
f_along:			DS		3
f_air:				DS		3
f_moment:			DS		4

sine_fine:			SINE_FINE_TABLE

					ALIGN	256
SQUARES_LOW:		SQUARES							; the low bytes, then the high 512 up
