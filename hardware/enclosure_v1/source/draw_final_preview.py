"""Render exported final STEP geometry and sliding interface section; mm."""
from Plots.instruments_v1.source.enclosure import cq,PROJECT
import math,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.patches import Polygon,Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
root=PROJECT/'final'
plt.rcParams['font.family']=['Malgun Gothic','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
fig=plt.figure(figsize=(15,10),facecolor='#f7f9fa')
fig.text(.045,.94,'1·2·3층 외장 시제품 · 최종 STL 구성',fontsize=25,weight='bold',color='#213b4a')
fig.text(.047,.895,'하우징 12조각 + 내부 부품 6개 / 모든 치수 mm / 모터·카메라 지지대 미포함',fontsize=12,color='#627d8b')
ax=fig.add_axes([.01,.17,.56,.69],projection='3d',facecolor='#f7f9fa')
for tier,names,rots,z,col,globalrot in [(1,['1_1']*4,[0,90,180,270],0,'#a3b6c3',0),(2,['2_1','2_2','2_1','2_2'],[0,90,180,270],100,'#80b6cd',20),(3,['3_1','3_2','3_1','3_2'],[0,90,180,270],201,'#ddbd89',0)]:
    for n,a in zip(names,rots):
        s=cq.importers.importStep(str(root/'step'/(n+'.step'))).val().rotate((0,0,0),(0,0,1),a+globalrot).translate((0,0,z))
        vv,ff=s.tessellate(.35,.18);v=np.array([[q.x,q.y,q.z] for q in vv]);tri=v[np.array(ff)]
        norms=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);norms/=np.maximum(np.linalg.norm(norms,axis=1)[:,None],1e-12)
        light=np.array([-.4,-.6,.7]);light/=np.linalg.norm(light);shade=.55+.45*np.abs(norms@light)
        ax.add_collection3d(Poly3DCollection(tri,facecolors=np.array(to_rgb(col))[None,:]*shade[:,None],edgecolors='none'))
ax.set_xlim(-105,105);ax.set_ylim(-105,105);ax.set_zlim(0,310);ax.set_box_aspect((1,1,1.65));ax.view_init(elev=20,azim=-58);ax.axis('off')
ax.set_title('조립된 외장 · 금속 하드웨어 생략',fontsize=12,color='#213b4a')
sec=fig.add_axes([.64,.42,.30,.36],facecolor='#f7f9fa')
lower=[(96,89),(100,89),(100,100),(97.4,100),(97.4,96),(94.6,96),(94.6,100),(92,100),(92,92),(96,92)]
upper=[(90,101),(95,101),(95,96),(97,96),(97,101),(100,101),(100,105),(90,105)]
sec.add_patch(Polygon(lower,facecolor='#a9d0e1',edgecolor='#365d72',linewidth=1.5))
sec.add_patch(Polygon(upper,facecolor='#e8cfa7',edgecolor='#876339',linewidth=1.5))
sec.plot([95,97],[96,96],color='#b0693d',lw=3)
sec.annotate('하중 지지 접촉면',(96,96),(91.5,94.1),fontsize=10,color='#986032',arrowprops={'arrowstyle':'->','color':'#986032'})
sec.annotate('',(100.6,100),(100.6,101),arrowprops={'arrowstyle':'<->','color':'#617f8d'});sec.text(100.9,100.3,'1',fontsize=10,color='#617f8d')
sec.text(92,106,'3층 바닥 + 돌기',fontsize=11,color='#876339');sec.text(92,87.5,'2층 상단 + 홈',fontsize=11,color='#365d72')
sec.set_xlim(89,103);sec.set_ylim(87,108);sec.set_aspect('equal');sec.axis('off');sec.set_title('미끄럼 연결 단면 · 반경 방향',fontsize=13,color='#213b4a')
for i,t in enumerate(['돌기 두께 2 / 홈 폭 2.8 / 양옆 여유 0.4',
 '돌기 길이 5 / 홈 깊이 4 / 하우징 간격 1',
 '원형 레일 평균 반경 R96 / 4분할 경계 후처리 필요',
 '층간 회전 토크·내마모성은 실물 시험 전']):fig.text(.61,.35-i*.041,'• '+t,fontsize=11,color='#405966')
fig.text(.047,.105,'출력용: stl/ 11종을 수량표에 따라 18개 출력. fit-test/ 2개 시험편은 별도.',fontsize=12,color='#405966')
fig.text(.047,.065,'조립 검증용: reference/assembly.step / 원본 치수와 검사 내역: README.md 및 reports/verification.json',fontsize=11,color='#405966')
fig.text(.047,.025,'180 mm 범위 확인은 부품 외곽 기준이며, 슬라이서·서포트와 실제 기계 동작은 검증하지 않았습니다.',fontsize=10,color='#986032')
fig.savefig(root/'preview.png',dpi=170,facecolor=fig.get_facecolor())
print(root/'preview.png',flush=True)
