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
;   bank 7, $C000   the second screen, paged in all the time
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
					ld		(steps_owed),a
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
; the steps the interrupt counted, and no keys yet (the controls come in a
; later stage).
read_input:
					ld		a,(test_mode)
					or		a
					jr		z,.live
					ld		hl,(test_keys)
					ld		a,(test_steps)
					jr		.cap
.live:				ld		hl,0
					di
					ld		a,(steps_owed)
					ld		c,a
					xor		a
					ld		(steps_owed),a
					ei
					ld		a,c
.cap:				cp		MAX_STEPS + 1
					ret		c
					ld		a,MAX_STEPS
					ret

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
steps_owed:			DB		0						; steps the interrupt has counted
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
					ld		hl,VIEW_DOWN			; turned as the Cub: the pitch
					ld		de,(state + STATE_PITCH)	; nose down, as fast3d has it,
					or		a						; and the line of sight below the
					sbc		hl,de					; datum
					ld		a,h
					ld		(camera_angles),a
					ld		a,(state + STATE_HEADING + 1)	; the heading and bank, the high
					ld		(camera_angles + 1),a	; bytes of the Cub's
					ld		a,(state + STATE_BANK + 1)
					ld		(camera_angles + 2),a
					call	set_camera
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


					INCLUDE	"fast3d.s"
					INCLUDE	"output/world_gen.s"

code_end:
					ASSERT	code_end <= IM2_ROUTINE

; Each object drawn: its points, from transform_object, in the four tables
; of 64 on one of these pages (POINT_PAGES, from build.py, is enough for
; every object at once), and its entry; and the lines cut at the near
; plane. In bank 5 above the screen, as fast3d's demo has them.
					ORG		$6000
point_pool:			DS		256 * POINT_PAGES
visible:			DS		VIS_SIZE * WORLD_OBJECTS
cut_lines:			DS		CUT_LINE_SIZE * CUT_LINES
					ASSERT	$ <= STACK_FLOOR

; The interrupt: a step owed to the flight model, and the screen flip_to
; asks for, if it asks.
					ORG		IM2_ROUTINE
interrupt:			push	af
					push	hl
					ld		hl,steps_owed			; (held at 255)
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
