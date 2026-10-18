; Cub: a Piper Cub flight simulator for the 128K, drawn with fast3d
; (examples/fast3d, beside this). So far the Cub stands tail down at the
; start of the runway, and each frame draws the cockpit view -- the
; airfield, black on cyan, and the horizon line -- above an empty panel in
; white on blue.
;
; Each frame is game.py's `frame` exactly, and tests/frames_test.py holds
; it to that: given the game state, the keys held and the steps owed, the
; next state and the screen drawn on. In the test mode (test_mode non-zero)
; the keys and the steps come from test_keys and test_steps instead of the
; keyboard and the interrupt, so that a harness can drive it a frame at a
; time with interrupts off.
;
; As fast3d's demo does, each frame is drawn on the screen not being shown
; and shown at the next interrupt; its arithmetic is done first, while the
; last frame waits to be shown.
;
;   bank 2, $8000   this and fast3d
;   bank 5, $4000   the first screen; at $6000 the points, the objects drawn
;                   and the lines cut at the near plane
;   bank 7, $C000   the second screen, paged in all the time; from $DB00
;                   the flight model (flight.s) and the panel (panel.s)
					DEVICE	ZXSPECTRUM128

					INCLUDE	"output/game_gen.s"		; game.py's constants, and the state's layout

					DEFINE	WORLD_WRAP 1			; the world wraps (fast3d's define)

STACK_FLOOR			EQU		$7E00					; the most the stack, from $8000, needs
IM2_TABLE			EQU		$BE00					; 257 bytes of $BD: wherever the
IM2_ROUTINE			EQU		$BDBD					; bus leaves the vector, $BDBD

					ORG		$8000

start:
					di
					ld		sp,$8000
					ld		hl,IM2_TABLE
					ld		de,IM2_TABLE + 1
					ld		bc,256
					ld		(hl),high IM2_ROUTINE
					ldir
					ld		a,high IM2_TABLE
					ld		i,a
					im		2
					call	setup
					ei
main_loop:
					call	game_frame
					jr		main_loop


; ---------------------------------------------------------------------------
; setup: as the Spectrum starts: bank 7 paged in at $C000, both screens
; blank with the view's and the panel's colours, the window lines are
; clipped to, and the game state as game.start_state has it. Leaves the
; interrupts as they are, so that frames_test.py can call it.

setup:
					ld		a,$17					; bank 7 at $C000, bank 5 shown,
					ld		bc,$7FFD				; ROM 1
					out		(c),a
					ld		a,1						; a blue border, as the panel
					out		($FE),a
					ld		hl,$4000
					call	clear_screen
					ld		hl,$C000
					call	clear_screen
					call	panel_still			; the panel's unchanging parts, on both
					ld		b,VIEW_LEFT
					ld		c,VIEW_TOP
					ld		d,VIEW_RIGHT
					ld		e,VIEW_BOTTOM
					call	set_window
					ld		hl,power_on_state
					ld		de,state
					ld		bc,STATE_SIZE
					ldir
					xor		a
					ld		(flip_to),a
					ld		(ticks_owed),a
					ret

; clear_screen: the screen at HL blank, the view's rows in its colours and
; the panel's in its own.
clear_screen:
					ld		d,h
					ld		e,l
					inc		de
					ld		(hl),0
					ld		bc,6143
					ldir
					inc		hl
					inc		de
					ld		(hl),VIEW_ATTRIBUTE
					ld		bc,32 * VIEW_ROWS - 1
					ldir
					inc		hl
					inc		de
					ld		(hl),PANEL_ATTRIBUTE
					ld		bc,32 * (24 - VIEW_ROWS) - 1
					ldir
					ret


; ---------------------------------------------------------------------------
; game_frame: one frame, game.frame: the keys and the steps owed, the clock,
; the view's arithmetic, then the view drawn on the screen `drawing` says,
; to be shown at the next interrupt.

game_frame:
					call	read_input				; HL = the keys, A = the steps
					ld		(state + STATE_KEYS),hl
					ld		e,a
					ld		d,0
					ld		hl,(state + STATE_CLOCK)
					add		hl,de
					ld		(state + STATE_CLOCK),hl
					ld		a,e						; the steps, through the flight
					or		a						; model, with the keys held
					jr		z,.flown
.step:				push	af
					call	flight_step
					pop		af
					dec		a
					jr		nz,.step
.flown:
					call	panel_frame			; what the panel shows, as it changed
					call	compute_frame
					call	wait_flip
					call	render_frame
					ld		a,(state + STATE_DRAWING)	; show it at the next interrupt
					or		a						; (bank 5's screen, or bank 7's),
					ld		a,$17					; and draw on the other next
					jr		z,.show
					ld		a,$1F
.show:				ld		(flip_to),a
					ld		a,(state + STATE_DRAWING)
					xor		1
					ld		(state + STATE_DRAWING),a
					ret

; read_input: HL = the keys held, A = the steps owed since the last frame,
; at most MAX_STEPS. In the test mode, from test_keys and test_steps; else
; the keys read_keys reads and the steps the interrupt counted.
read_input:
					ld		a,(test_mode)
					or		a
					jr		z,.live
					ld		hl,(test_keys)
					ld		a,(test_steps)
					jr		.cap
.live:				call	read_keys
					di
					ld		a,(ticks_owed)			; a step every 1 << STEP_SHIFT ticks: the
					ld		c,a						; ticks left over wait for the
					and		(1 << STEP_SHIFT) - 1	; next frame
					ld		(ticks_owed),a
					ei
					ld		a,c
					REPT	STEP_SHIFT
					srl		a
					EDUP
.cap:				cp		MAX_STEPS + 1
					ret		c
					ld		a,MAX_STEPS
					ret

; read_keys: HL = the keys held, as keys.py's bits: the keyboard, and an
; Interface II joystick in either of its ports, which read as the keys 6 to
; 0 and 1 to 5 -- left, right, down, up and fire. Down pulls the stick back,
; and fire is the brakes. Uses AF, DE, HL, IX.
read_keys:
					ld		hl,0
					ld		ix,key_map
.key:
					ld		a,(ix + 0)				; the half-row
					or		a
					ret		z
					in		a,($FE)
					and		(ix + 1)				; the key's bit: 0 is held
					jr		nz,.next
					ld		a,l
					or		(ix + 2)
					ld		l,a
					ld		a,h
					or		(ix + 3)
					ld		h,a
.next:
					ld		de,4
					add		ix,de
					jr		.key

; Each key: its half-row's port high byte, its bit there, and its bit in
; the keys held.
key_map:
					DB		$FB, $01
					DW		KEY_THROTTLE_UP			; Q
					DB		$FD, $01
					DW		KEY_THROTTLE_DOWN		; A
					DB		$FE, $02
					DW		KEY_RUDDER_LEFT			; Z
					DB		$FE, $04
					DW		KEY_RUDDER_RIGHT		; X
					DB		$7F, $01
					DW		KEY_BRAKES				; Space
					DB		$FE, $10
					DW		KEY_VIEW				; V
					DB		$7F, $08
					DW		KEY_NEW_FLIGHT			; N
					DB		$EF, $10
					DW		KEY_STICK_LEFT			; 6, Interface II's first port
					DB		$EF, $08
					DW		KEY_STICK_RIGHT			; 7
					DB		$EF, $04
					DW		KEY_STICK_BACK			; 8, down
					DB		$EF, $02
					DW		KEY_STICK_FORWARD		; 9, up
					DB		$EF, $01
					DW		KEY_BRAKES				; 0, fire
					DB		$F7, $01
					DW		KEY_STICK_LEFT			; 1, its second port
					DB		$F7, $02
					DW		KEY_STICK_RIGHT			; 2
					DB		$F7, $04
					DW		KEY_STICK_BACK			; 3, down
					DB		$F7, $08
					DW		KEY_STICK_FORWARD		; 4, up
					DB		$F7, $10
					DW		KEY_BRAKES				; 5, fire
					DB		0

; wait_flip: until the interrupt has shown the last frame. In the test mode
; there are no interrupts, so it shows it itself.
wait_flip:
					ld		a,(test_mode)
					or		a
					jr		nz,.now
.wait:				ld		a,(flip_to)
					or		a
					ret		z
					halt
					jr		.wait
.now:				ld		a,(flip_to)
					or		a
					ret		z
					ld		bc,$7FFD
					out		(c),a
					xor		a
					ld		(flip_to),a
					ret

flip_to:			DB		0						; non-zero: what the next interrupt
													; writes to port $7FFD
ticks_owed:			DB		0						; fiftieths the interrupt has counted
test_mode:			DB		0						; non-zero: frames_test.py drives it
test_keys:			DW		0						; and these are the keys held
test_steps:			DB		0						; and the steps owed

state:												; the game state (game.STATE_LAYOUT)
					DS		STATE_SIZE
power_on_state:
					POWER_ON_STATE


; ---------------------------------------------------------------------------
; compute_frame: the camera at the pilot's eye, and what it sees, touching
; no screen: each object in view has its points in the pool, its edges cut
; at the near plane in cut_lines, and an entry in `visible`.

; An entry in `visible`, for an object drawn.
VIS_PAGE			EQU		0						; its points' page
VIS_BASE			EQU		1						; and its first vertex there
VIS_EDGES			EQU		2						; how many edges, and where
VIS_SIZE			EQU		5
POINTS_ROOM			EQU		POINTS_X_HI				; points a page holds: each of its
													; four tables has 64
CUT_LINE_SIZE		EQU		8						; a cut line: x0, y0, x1, y1, 16-bit

compute_frame:
					ld		hl,(state + STATE_X + 2)	; the eye, EYE_HEIGHT above the
					ld		(camera_x),hl			; main wheels: whole feet, the
					ld		hl,(state + STATE_Y + 2)	; positions being 16.16
					ld		de,EYE_HEIGHT
					add		hl,de
					ld		(camera_y),hl
					ld		hl,(state + STATE_Z + 2)
					ld		(camera_z),hl
					call	camera_matrix			; turned as the Cub
					call	set_camera_matrix
					xor		a
					ld		(drawn),a
					ld		(cuts),a
					ld		hl,cut_lines
					ld		(.cut_at),hl
					ld		hl,visible
					ld		(.entry),hl
					ld		hl,point_pool			; the pool's first page, from 0
					ld		(.slot),hl
					ld		ix,world				; every object: IX walks them,
					ld		a,WORLD_OBJECTS			; and cull_object keeps IX
					ld		(.objects_left),a
.object:			call	cull_object
					jr		c,.next					; out of view
					call	fine_centre			; T, put right
					ld		(.object_at),ix			; (object_matrix and
					ld		hl,drawn				; transform_object do not)
					inc		(hl)
					call	object_matrix
					ld		ix,(.object_at)
					ld		l,(ix + OBJECT_MODEL)
					ld		h,(ix + OBJECT_MODEL + 1)
					ld		b,(hl)					; MODEL_VERTICES
					ld		de,(.slot)				; room for them on this page?
					ld		a,e
					add		a,b
					cp		POINTS_ROOM + 1
					jr		c,.room
					inc		d						; else on the next, from 0
					ld		e,0
					ld		a,b
.room:				ld		(.first),de
					ld		e,a
					ld		(.slot),de				; where the next object's go
					ld		de,(.first)
					call	transform_object
					ld		a,(transform_behind)	; the edges cut at the near
					or		a						; plane, if any vertex is behind
					jr		z,.entry_now			; it (CUT_LINES is room for
					ld		ix,(.object_at)			; every edge at once)
					ld		hl,(.first)
					ld		de,(.cut_at)
					call	cut_edges
					ld		(.cut_at),de
					ld		hl,cuts
					add		a,(hl)
					ld		(hl),a
.entry_now:			ld		de,(.entry)				; and the entry
					ld		a,(.first + 1)
					ld		(de),a					; VIS_PAGE
					inc		de
					ld		a,(.first)
					ld		(de),a					; VIS_BASE
					inc		de
					ld		a,(view_edge_count)		; VIS_EDGES: the count, and
					ld		(de),a					; where they are
					inc		de
					ld		hl,(view_edges)
					ex		de,hl
					ld		(hl),e
					inc		hl
					ld		(hl),d
					inc		hl
					ld		(.entry),hl
					ld		ix,(.object_at)
.next:				ld		de,OBJECT_SIZE
					add		ix,de
					ld		hl,.objects_left
					dec		(hl)
					jp		nz,.object
					ret

.object_at:			DW		0						; the one being drawn
.objects_left:		DB		0
.entry:				DW		0						; -> the next entry in visible
.slot:				DW		0						; where the next points go: the
													; vertex, then the page
.first:				DW		0						; and where this object's went
.cut_at:			DW		0						; where the next cut line goes
drawn:				DB		0						; objects drawn this frame
cuts:				DB		0						; lines cut at the near plane


; ---------------------------------------------------------------------------
; render_frame: on the screen `drawing` says, the view cleared, then the
; horizon, every edge of the objects in view with both ends in front of the
; near plane, and the lines cut at it, all clipped to the view.

; L = a vertex's number, H = the points' page: its x and y into TO_X and
; TO_X + 2, as clip_line takes them, or on to SKIP_TO if it is behind the
; near plane. Keeps B and C.
					MACRO	END_AT TO_X, SKIP_TO
					set		6,l
					ld		a,(hl)					; POINTS_X_HI
					cp		high WIDE_BEHIND
					jr		z,SKIP_TO
					ld		d,a
					res		6,l
					ld		e,(hl)					; POINTS_X_LO
					ld		(TO_X),de
					set		7,l
					ld		e,(hl)					; POINTS_Y_LO
					set		6,l
					ld		d,(hl)					; POINTS_Y_HI
					ld		(TO_X + 2),de
					ENDM

render_frame:
					ld		a,(state + STATE_DRAWING)	; 0: $4000, 1: $C000
					rrca
					ld		(screen_high),a
					ld		b,VIEW_BOTTOM - VIEW_TOP + 1	; the whole view cleared
					ld		c,VIEW_TOP
					ld		d,0
					ld		e,32
					call	clear_box
					call	draw_horizon
					ld		a,(drawn)
					or		a
					jp		z,.cut_lines
					ld		hl,visible
.object:			ld		(.objects_left),a
					ld		a,(hl)					; VIS_PAGE and VIS_BASE, into
					ld		(.page + 1),a			; the code below
					inc		hl
					ld		a,(hl)
					ld		(.base1 + 1),a
					ld		(.base2 + 1),a
					inc		hl
					ld		a,(hl)					; VIS_EDGES
					inc		hl
					ld		e,(hl)
					inc		hl
					ld		d,(hl)
					inc		hl
					ld		(.entry),hl
					ld		(.edge_at),de
					or		a
					jr		z,.next_object
.edge:				ld		(.edges_left),a
					ld		hl,(.edge_at)
					ld		a,(hl)					; its ends
					inc		hl
.base1:				add		a,0
					ld		b,a
					ld		a,(hl)
					inc		hl
					ld		(.edge_at),hl
.base2:				add		a,0
					ld		c,a
.page:				ld		h,0
					ld		l,b
					END_AT	clip_x0, render_frame.next_edge	; neither behind the plane
					ld		l,c
					END_AT	clip_x1, render_frame.next_edge
					call	clip_line
					call	nc,draw_line			; (carry: none of it in view)
.next_edge:			ld		a,(.edges_left)
					dec		a
					jr		nz,.edge
.next_object:		ld		hl,(.entry)
					ld		a,(.objects_left)
					dec		a
					jr		nz,.object
.cut_lines:			ld		a,(cuts)				; the edges cut at the near
					or		a						; plane: each line, front end
					ret		z						; then the cut
					ld		hl,cut_lines
.cut_line:			ld		(.edges_left),a
					ld		de,clip_x0
					ld		bc,CUT_LINE_SIZE
					ldir
					ld		(.edge_at),hl
					call	clip_line
					call	nc,draw_line
					ld		hl,(.edge_at)
					ld		a,(.edges_left)
					dec		a
					jr		nz,.cut_line
					ret

.objects_left:		DB		0
.entry:				DW		0
.edges_left:		DB		0
.edge_at:			DW		0


; ---------------------------------------------------------------------------
; draw_horizon: the horizon line, game.horizon_line. u, the world's up in
; camera space, is Rc's middle row: camera_seen, Rc^T, has it as its middle
; column. Mostly level (|u_x| <= |u_y|), the line runs from x = centre - R
; to centre + R (R = HORIZON_REACH) at y = centre + a -+ b, with
; a = 256 u_z / u_y (256 being fast3d's focal length) and b = R u_x / u_y;
; banked steeper, from y = centre - R to centre + R at x = centre + a -+ b,
; with a = -256 u_z / u_x and b = R u_y / u_x.
; Each divide is divide_wide's, of a 16-bit numerator by the divisor's size,
; its sign put on the numerator. Then clip_line, and draw_line if any of it
; is in view.

draw_horizon:
					ld		a,(camera_seen + 1)
					ld		(.u_x),a
					call	.size
					ld		b,a						; B = |u_x|
					ld		a,(camera_seen + 4)
					ld		(.u_y),a
					call	.size					; A = |u_y|
					cp		b
					jr		c,.steep
					or		a
					ret		z						; u_x = u_y = 0: straight up or down
					ld		c,a						; C = |u_y|, the divisor
					ld		a,(.u_y)
					ld		(.sign),a
					ld		(.a_sign),a
					call	.a_term					; HL = a: 256 u_z / u_y
					push	hl
					ld		a,(.u_x)
					call	.b_term					; HL = b: 128 u_x / u_y
					ex		de,hl
					pop		hl
					ld		bc,SCREEN_CENTRE_Y
					add		hl,bc					; HL = centre + a, DE = b
					push	hl
					or		a
					sbc		hl,de
					ld		(clip_y0),hl
					pop		hl
					add		hl,de
					ld		(clip_y1),hl
					ld		hl,SCREEN_CENTRE_X - HORIZON_REACH
					ld		(clip_x0),hl
					ld		hl,SCREEN_CENTRE_X + HORIZON_REACH
					ld		(clip_x1),hl
					jr		.draw
.steep:				ld		c,b						; C = |u_x|, the divisor
					ld		a,(.u_x)
					ld		(.sign),a
					cpl								; (a's numerator takes the
					ld		(.a_sign),a				; other sign: -256 u_z)
					call	.a_term					; HL = a: -256 u_z / u_x
					push	hl
					ld		a,(.u_y)
					call	.b_term					; HL = b: 128 u_y / u_x
					ex		de,hl
					pop		hl
					ld		bc,SCREEN_CENTRE_X
					add		hl,bc					; HL = centre + a, DE = b
					push	hl
					or		a
					sbc		hl,de
					ld		(clip_x0),hl
					pop		hl
					add		hl,de
					ld		(clip_x1),hl
					ld		hl,SCREEN_CENTRE_Y - HORIZON_REACH
					ld		(clip_y0),hl
					ld		hl,SCREEN_CENTRE_Y + HORIZON_REACH
					ld		(clip_y1),hl
.draw:				call	clip_line
					ret		c
					jp		draw_line

; HL = 256 u_z, negative if .a_sign is, / C. Keeps C.
.a_term:			ld		a,(camera_seen + 7)		; u_z
					ld		h,a
					ld		l,0
					ld		a,(.a_sign)
					jr		.divide
; HL = HORIZON_REACH A, negative if .sign is, / C. Keeps C.
					ASSERT	HORIZON_REACH == 128	; (A * 256, halved)
.b_term:			ld		h,a
					ld		l,0
					sra		h
					rr		l
					ld		a,(.sign)
.divide:			or		a						; the divisor's sign on the
					call	m,negate_hl				; numerator (fast3d's)
					jp		divide_wide

; A = |A|.
.size:				or		a
					ret		p
					neg
					ret

.u_x:				DB		0
.u_y:				DB		0
.sign:				DB		0						; the divisor's
.a_sign:			DB		0						; and the sign a's numerator takes


; ---------------------------------------------------------------------------
; camera_matrix: Rc^T into fast3d's matrix_t, for set_camera_matrix, from
; the Cub's attitude in its full 16 bits (game.camera_matrix): the line of
; sight's pitch x = VIEW_DOWN - pitch, the heading y and the roll z = -bank,
; Rc = Ry Rx Rz. Each product is Q15's, in game.camera_matrix's order, and
; each entry rounded to a byte, 127 for 1.0. Uses everything but IY and the
; alternate registers.

; DE = (FIRST)(SECOND), Q15.
					MACRO	PRODUCT	FIRST, SECOND
					ld		bc,(FIRST)
					ld		de,(SECOND)
					call	q15
					ENDM

; Rc's entry at ROW, COLUMN from DE, into matrix_t, which holds Rc^T row by
; row (Rc's columns), and what its rounding left out into fine_t, the same
; way round.
					MACRO	ENTRY_AT	ROW, COLUMN
					call	matrix_entry
					ld		(matrix_t + 3 * COLUMN + ROW),a
					ld		a,e
					ld		(fine_t + 3 * COLUMN + ROW),a
					ENDM

camera_matrix:
					ld		hl,VIEW_DOWN			; x, nose down as fast3d has it
					ld		de,(state + STATE_PITCH)
					or		a
					sbc		hl,de
					ld		ix,camera_sx
					call	sine_cosine
					ld		hl,(state + STATE_HEADING)	; y
					ld		ix,camera_sy
					call	sine_cosine
					ld		hl,0					; z, the view's right side up
					ld		de,(state + STATE_BANK)	; with the Cub banked left
					or		a
					sbc		hl,de
					ld		ix,camera_sz
					call	sine_cosine
					PRODUCT	camera_sx, camera_sz
					ld		(camera_sxsz),de
					PRODUCT	camera_sx, camera_cz
					ld		(camera_sxcz),de

					PRODUCT	camera_cy, camera_cz	; m00 = cy cz + sy sxsz
					push	de
					PRODUCT	camera_sy, camera_sxsz
					pop		hl
					add		hl,de
					ex		de,hl
					ENTRY_AT	0, 0
					PRODUCT	camera_sy, camera_sxcz	; m01 = sy sxcz - cy sz
					push	de
					PRODUCT	camera_cy, camera_sz
					pop		hl
					or		a
					sbc		hl,de
					ex		de,hl
					ENTRY_AT	0, 1
					PRODUCT	camera_sy, camera_cx	; m02 = sy cx
					ENTRY_AT	0, 2
					PRODUCT	camera_cx, camera_sz	; m10 = cx sz
					ENTRY_AT	1, 0
					PRODUCT	camera_cx, camera_cz	; m11 = cx cz
					ENTRY_AT	1, 1
					ld		hl,0					; m12 = -sx
					ld		de,(camera_sx)
					or		a
					sbc		hl,de
					ex		de,hl
					ENTRY_AT	1, 2
					PRODUCT	camera_cy, camera_sxsz	; m20 = cy sxsz - sy cz
					push	de
					PRODUCT	camera_sy, camera_cz
					pop		hl
					or		a
					sbc		hl,de
					ex		de,hl
					ENTRY_AT	2, 0
					PRODUCT	camera_sy, camera_sz	; m21 = sy sz + cy sxcz
					push	de
					PRODUCT	camera_cy, camera_sxcz
					pop		hl
					add		hl,de
					ex		de,hl
					ENTRY_AT	2, 1
					PRODUCT	camera_cy, camera_cx	; m22 = cy cx
					ENTRY_AT	2, 2
					ret

; sine_cosine: the sine and cosine of the angle HL, Q15, into the two words
; at IX. Uses everything but IX, IY and the alternate registers.
sine_cosine:
					push	hl
					call	sin16
					ld		(ix + 0),e
					ld		(ix + 1),d
					pop		hl
					ld		de,$4000				; a quarter turn on
					add		hl,de
					call	sin16
					ld		(ix + 2),e
					ld		(ix + 3),d
					ret

; sin16: DE = the sine of the angle HL, 65,536 to the turn, Q15, as
; flight.sin16: sine_table's two entries either side, interpolated by the
; low byte, floored: s0 + (((s1 - s0) fraction) >> 8), the product by
; umul16's byte rounds. Uses everything but IX, IY and the alternate
; registers.
sin16:
					ld		a,l						; the fraction
					ld		(.fraction),a
					ld		l,h
					ld		h,0
					add		hl,hl
					ld		de,sine_table
					add		hl,de
					ld		e,(hl)					; DE = s0
					inc		hl
					ld		d,(hl)
					inc		hl
					ld		a,(hl)					; HL = s1
					inc		hl
					ld		h,(hl)
					ld		l,a
					push	de
					or		a
					sbc		hl,de					; HL = s1 - s0, within +-805
					ld		a,h
					ld		(.sign),a
					bit		7,h
					jr		z,.size
					xor		a
					sub		l
					ld		l,a
					sbc		a,a
					sub		h
					ld		h,a
.size:
					ld		b,h
					ld		c,l
					ld		a,(.fraction)
					ld		e,a
					ld		d,0
					call	umul16					; E:HL = |s1 - s0| times the fraction
					ld		a,(.sign)
					or		a
					jp		p,.positive
					xor		a						; negative: E:HL = -E:HL
					sub		l
					ld		l,a
					ld		a,0
					sbc		a,h
					ld		h,a
					ld		a,0
					sbc		a,e
					ld		e,a
.positive:
					ld		l,h						; >> 8
					ld		h,e
					pop		de
					add		hl,de
					ex		de,hl
					ret
.fraction:			DB		0
.sign:				DB		0

; q15: DE = BC DE >> 15, floored (game.q15): the high word of the product
; shifted left once. Uses everything but IX, IY and the alternate registers.
q15:
					call	multiply
					add		hl,hl
					rl		e
					rl		d
					ret

; multiply: DE:HL = BC DE, signed 16 bits by 16 into 32. Uses everything but
; IX, IY and the alternate registers.
multiply:
					ld		a,b
					xor		d
					push	af						; the product's sign, in S
					bit		7,b
					jr		z,.bc_size
					xor		a
					sub		c
					ld		c,a
					sbc		a,a
					sub		b
					ld		b,a
.bc_size:
					bit		7,d
					jr		z,.de_size
					xor		a
					sub		e
					ld		e,a
					sbc		a,a
					sub		d
					ld		d,a
.de_size:
					ld		hl,0					; DE:HL = BC DE, unsigned: DE
					ld		a,16					; shifts out at the top as the
.bit:
					add		hl,hl					; product shifts in below
					rl		e
					rl		d
					jr		nc,.next
					add		hl,bc
					jr		nc,.next
					inc		de
.next:
					dec		a
					jr		nz,.bit
					pop		af
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

; matrix_entry: A = (127 DE + 16,384) >> 15, a Q15 entry as fast3d keeps it,
; 127 for 1.0 (game.matrix_entry), and E = what that left out, in 32nds of
; its unit (game.matrix_residual): (127 DE + 512) >> 10 less 32 A, of which
; only the low byte is needed, the residual being within +-16. C:H:L = 128
; DE - DE, 24 bits; A its bits 15 to 22, rounded; E (C:H + 2) >> 2's low
; byte, less 32 times A's low three bits. Uses AF, BC, DE, HL.
matrix_entry:
					ld		c,d						; C:H:L = DE 256 / 2
					ld		h,e
					ld		l,0
					sra		c
					rr		h
					rr		l
					ld		a,d						; B = DE's sign, for its top byte
					rla
					sbc		a,a
					ld		b,a
					or		a
					sbc		hl,de					; less DE
					ld		a,c
					sbc		a,b
					ld		c,a
					ld		a,h						; E = (C:H + 2) >> 2's low byte
					add		a,2
					ld		e,a
					ld		a,c
					adc		a,0
					sra		a
					rr		e
					sra		a
					rr		e
					push	de
					ld		de,16384				; rounded
					add		hl,de
					ld		a,c
					adc		a,0
					add		hl,hl					; A = bits 15..22
					rla
					pop		de
					ld		b,a						; E less 32 A, in its low byte
					and		7
					rrca
					rrca
					rrca
					ld		c,a
					ld		a,e
					sub		c
					ld		e,a
					ld		a,b
					ret

; ---------------------------------------------------------------------------
; fine_centre: view_t, the centre cull_object has just let through, with
; what the rounding of Rc's entries left out put back (game.fine_centre):
; on each axis, (fine_t's row times d + 16) >> 5, d = P - C, the object at
; IX's position less the camera's. Keeps IX. Uses everything else but IY
; and the alternate registers.
fine_centre:
					ld		l,(ix + OBJECT_X)		; d, 16 bits each way, wrapping
					ld		h,(ix + OBJECT_X + 1)	; as the world does
					ld		de,(camera_x)
					or		a
					sbc		hl,de
					ld		(fine_d),hl
					ld		l,(ix + OBJECT_X + 2)
					ld		h,(ix + OBJECT_X + 3)
					ld		de,(camera_y)
					or		a
					sbc		hl,de
					ld		(fine_d + 2),hl
					ld		l,(ix + OBJECT_X + 4)
					ld		h,(ix + OBJECT_X + 5)
					ld		de,(camera_z)
					or		a
					sbc		hl,de
					ld		(fine_d + 4),hl
					ld		hl,fine_t				; fine_row walks fine_t's rows,
					ld		(fine_row),hl
					ld		hl,view_t				; and HL view_t's axes
					ld		b,3
.axis:
					push	bc
					push	hl
					ld		hl,0					; the row times d, 24 bits, in
					ld		(fine_sum),hl			; fine_sum
					xor		a
					ld		(fine_sum + 2),a
					ld		de,(fine_d)
					call	fine_term
					ld		de,(fine_d + 2)
					call	fine_term
					ld		de,(fine_d + 4)
					call	fine_term
					ld		hl,(fine_sum)			; C:H = (it + 16) >> 5
					ld		a,(fine_sum + 2)
					ld		c,a
					ld		de,16
					add		hl,de
					jr		nc,.rounded
					inc		c
.rounded:
					add		hl,hl
					rl		c
					add		hl,hl
					rl		c
					add		hl,hl
					rl		c
					ld		e,h						; DE, 16 bits
					ld		d,c
					ld		a,c						; C = its sign, for the top byte
					rla
					sbc		a,a
					ld		c,a
					pop		hl						; view_t's axis += it
					ld		a,(hl)
					add		a,e
					ld		(hl),a
					inc		hl
					ld		a,(hl)
					adc		a,d
					ld		(hl),a
					inc		hl
					ld		a,(hl)
					adc		a,c
					ld		(hl),a
					inc		hl
					pop		bc
					djnz	.axis
					ret

; fine_term: fine_sum += the residual at fine_row, a signed byte within
; +-16, times DE, signed 16 bits: 24 bits, by five rounds of shift and add;
; fine_row on to the next. Uses AF, BC, DE, HL.
fine_term:
					ld		hl,(fine_row)
					ld		a,(hl)
					inc		hl
					ld		(fine_row),hl
					or		a
					jp		p,.size
					neg								; A = |A|, and DE negated for it
					ld		c,a
					xor		a
					sub		e
					ld		e,a
					sbc		a,a
					sub		d
					ld		d,a
					ld		a,c
.size:
					add		a,a						; B = the multiplier, its bit 4 at
					add		a,a						; the top
					add		a,a
					ld		b,a
					ld		a,d						; C = DE's sign, for its top byte
					rla
					sbc		a,a
					ld		c,a
					xor		a						; A:H:L = B DE
					ld		h,a
					ld		l,a
					REPT	5
					add		hl,hl
					rla
					sla		b						; the multiplier's next bit, the
					jr		nc,$ + 4				; highest first
					add		hl,de
					adc		a,c
					EDUP
					ld		de,(fine_sum)			; fine_sum += A:H:L
					add		hl,de
					ld		(fine_sum),hl
					ld		e,a
					ld		a,(fine_sum + 2)
					adc		a,e
					ld		(fine_sum + 2),a
					ret

fine_t:				DS		9						; Rc^T's residuals, row by row
fine_d:				DS		6						; P - C
fine_sum:			DS		3
fine_row:			DW		0

camera_sx:			DW		0						; sine_cosine's: sin, cos
camera_cx:			DW		0
camera_sy:			DW		0
camera_cy:			DW		0
camera_sz:			DW		0
camera_cz:			DW		0
camera_sxsz:		DW		0
camera_sxcz:		DW		0

sine_table:			SINE_TABLE						; flight.SINE: 32,767 sin, 257 words


					INCLUDE	"fast3d.s"
					INCLUDE	"output/world_gen.s"

code_end:
					ASSERT	code_end <= IM2_ROUTINE

; The flight model, in bank 7 above its screen: paged in at $C000 all the
; time, and the screen ends at $DAFF.
					SLOT	3
					PAGE	7
					ORG		$DB00
					INCLUDE	"flight.s"
					INCLUDE	"panel.s"
flight_end:
					ASSERT	flight_end <= $10000

; Each object drawn: its points, from transform_object, in the four tables
; of 64 on one of these pages (POINT_PAGES, from build.py, is enough for
; every object at once), and its entry; and the lines cut at the near
; plane. In bank 5 above the screen, as fast3d's demo has them.
					ORG		$6000
point_pool:			DS		256 * POINT_PAGES
visible:			DS		VIS_SIZE * WORLD_OBJECTS
cut_lines:			DS		CUT_LINE_SIZE * CUT_LINES
					ASSERT	$ <= STACK_FLOOR

; The interrupt: a tick counted, of which every two owe the flight model a
; step, and the screen flip_to asks for, if it asks.
					ORG		IM2_ROUTINE
interrupt:			push	af
					push	hl
					ld		hl,ticks_owed			; (held at 255)
					inc		(hl)
					jr		nz,.counted
					dec		(hl)
.counted:			ld		a,(flip_to)
					or		a
					jr		z,.done
					push	bc
					ld		bc,$7FFD
					out		(c),a
					pop		bc
					xor		a
					ld		(flip_to),a
.done:				pop		hl
					pop		af
					ei
					ret
end:
					ASSERT	end <= IM2_TABLE
					SAVEDEV	"output/cub.banks", 0, 0, $20000
